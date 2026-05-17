import argparse
import csv
import datetime
import logging
import time
import os
import re
import threading
import queue
from strenum import StrEnum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from orthanc_api_client import OrthancApiClient, InstancesSet, ResourceType, ResourceNotFound, exceptions
from .orthanc_monitor import ChangeType

logger = logging.getLogger(__name__)
UNKNOWN_LOG_CONTEXT_VALUE = "unknown"
REMOTE_AET_METADATA_NAMES = ("RemoteAET", "RemoteAet")

class ForwarderMode(StrEnum):
    DICOM = 'dicom'             # use DICOM
    DICOM_SERIES_BY_SERIES = 'dicom-series-by-series'             # use DICOM but create a new association for each series
    DICOM_WEB = 'dicom-web'     # use DicomWEB
    DICOM_WEB_SERIES_BY_SERIES = 'dicom-web-series-by-series'     # use DicomWEB but one request per series to avoid large payloads.  This will also split very large series into < 1GB requests
    PEERING = 'peering'         # use peering between 2 orthancs
    TRANSFER = 'transfer'       # use the transfer plugin accelerator between 2 orthancs


class StudyDescriptionMatchType(StrEnum):
    SUBSTRING = 'substring'
    REGEX = 'regex'


@dataclass
class ForwarderDestination:
    destination: str                        # the alias of the destination Modality, Peer or DicomWeb server
    forwarder_mode: ForwarderMode           # the mode to use to forward to the destination
    alternate_destination: str = None       # an alternate destination in case this one can not be contacted
    study_description_match_type: Optional[StudyDescriptionMatchType] = None
    study_description_pattern: Optional[str] = None
    _compiled_study_description_regex: Optional[re.Pattern] = field(init=False, default=None, repr=False)

    def __post_init__(self):
        if isinstance(self.study_description_match_type, str):
            normalized_match_type = self.study_description_match_type.strip().lower()
            valid_match_types = {m.value for m in StudyDescriptionMatchType}
            if normalized_match_type not in valid_match_types:
                raise ValueError(
                    f"Invalid StudyDescription match type '{self.study_description_match_type}' "
                    f"for destination '{self.destination}'. Allowed values: {sorted(valid_match_types)}"
                )
            self.study_description_match_type = StudyDescriptionMatchType(normalized_match_type)

        if self.study_description_match_type is None:
            self.study_description_pattern = None
            return

        if self.study_description_pattern is not None:
            self.study_description_pattern = self.study_description_pattern.strip()

        if not self.study_description_pattern:
            raise ValueError(f"StudyDescription filter pattern is missing for destination '{self.destination}'.")

        if self.study_description_match_type == StudyDescriptionMatchType.REGEX:
            try:
                self._compiled_study_description_regex = re.compile(self.study_description_pattern, re.IGNORECASE)
            except re.error as ex:
                raise ValueError(
                    f"Invalid StudyDescription regex for destination '{self.destination}': {ex}"
                ) from ex

    @property
    def retry_key(self) -> str:
        match_type = self.study_description_match_type or ''
        pattern = self.study_description_pattern or ''
        return f"{self.forwarder_mode}:{self.destination}:{match_type}:{pattern}"

    def matches_study_description(self, study_description: Optional[str]) -> bool:
        if self.study_description_match_type is None:
            return True

        if not study_description:
            return False

        if self.study_description_match_type == StudyDescriptionMatchType.SUBSTRING:
            return self.study_description_pattern.lower() in study_description.lower()

        if self.study_description_match_type == StudyDescriptionMatchType.REGEX:
            return self._compiled_study_description_regex.search(study_description) is not None

        raise NotImplementedError(f"Unsupported StudyDescription match type: {self.study_description_match_type}")

@dataclass
class ResourceToForward:
    type: str
    resource_id: str

# class ForwarderMetadata(Enum):
#     INSTANCE_PROCESSED = 4600
#     SENT_TO_DESTINATIONS = 4601
#     NEXT_RETRY = 4602


@dataclass
class ForwarderInstancesSetStatus:
    processed: bool = field(init=False, default=False)
    sent_to_destinations: List[str] = field(default_factory=list)
    last_eligible_destinations: List[str] = field(default_factory=list)
    retry_count: int = field(init=False, default=0)
    next_retry: Optional[datetime.datetime] = None
    terminal: bool = field(init=False, default=False)
    log_context: Optional[str] = None


class OrthancForwarder:
    """
    Forwards everything Orthanc receives to another Orthanc peer, a DICOM modality or DicomWeb server.
    The Forwarder deletes the study/instances once they have been forwarded.

    The images may be modified before being sent.  In that case, you should:
    - either provide an instance_processor callback if you are modifying the instances 'in_place' (keeping the same Orthanc ids)
    - or override process() in a subclass
    The modifications shall be idempotent:  it shall always give the same result if you repeat the modification multiple times

    The images may be filtered out before being processed and forwarded.  In that case, you should:
    - either provide an instance_filter callback
    - or override filter() in a subclass
    Images that are filtered out are deleted from the forwarder.

    You may also provide a few callbacks e.g to log events:
    - on_instances_set_forwarded()
    - on_instances_set_forward_error()

    An OrthancForwarder may be triggered by two 'events': the stable study or the 'instance received' event.

    You might define multiple destinations -> the Forwarder will send the study to all destinations and delete the study only once the study has been sent to all destinations.
    i.e: destinations = [Destination(A, PEER), Destination(B, DICOM)]
    -> it will send to A and B

    You might also define alternate destinations that will be used when the primary destination is unreachable.
    i.e: destinations = [Destination(A, PEER, alternateDestination = Destination(B, DICOM))]
    -> it will try to send to A and, if A is down, will send to B

    If the forwarding fails, the Forwarder will retry to send the instances later on.

    The OrthancForwarder uses Orthanc metadata ranging between [4600, 4700[
    """

    retry_intervals = [60, 120, 300, 1800, 3600]

    def __init__(self,
                 source: OrthancApiClient,
                 destinations: List[ForwarderDestination],
                 trigger: ChangeType = ChangeType.STABLE_STUDY,
                 max_retry_count_at_startup: int = 5,
                 polling_interval_in_seconds: int = 1,
                 worker_threads_count: int = 3,
                 instance_filter = None,                    # a method to filter instances.  Signature: Filter(api_client, instance_id) -> bool (returns True to keep an instance, returns False to delete it)
                 instance_processor = None,                 # a method to process instances before forwarding them.  Signature: Process(api_client, instance_id)
                 on_instances_set_forwarded = None,         # a method that is called each time an InstancesSet has been forwarded to a destination.  Signature: forwarded(instances_set, destination)
                 on_instances_set_forward_error = None      # a method that is called each time an InstancesSet has failed to be forwarded to a destination.  Signature: forward_error(instances_set, destination, error)
                 ):

        self._source = source
        self._destinations = destinations
        self._trigger = trigger
        self._max_retry_count_at_startup = max_retry_count_at_startup
        self._polling_interval_in_seconds = polling_interval_in_seconds
        self._is_running = False
        self._execution_thread = None
        self._instance_filter = instance_filter
        self._instance_processor = instance_processor
        self._on_instances_set_forwarded = on_instances_set_forwarded
        self._on_instances_set_forward_error = on_instances_set_forward_error
        self._status = {}
        self._resources_to_process = queue.Queue(worker_threads_count + 1)
        self._worker_threads_count = worker_threads_count
        self._worker_threads = []
        self._is_running = False

    def wait_orthanc_started(self):
        retry = 0
        while not self._source.is_alive():
            logger.info("Waiting to connect to Orthanc")
            retry += 1
            if retry == self._max_retry_count_at_startup:
                logger.error("Could not connect to Orthanc at startup")
                raise Exception("Could not connect to Orthanc at startup")
            time.sleep(self._polling_interval_in_seconds)

        system = self._source.get_system()
        if "OverwriteInstances" not in system:
            logger.warning("Unable to check OverwriteInstances configuration")
        elif not system["OverwriteInstances"]:
            if self._instance_processor:
                logger.error("Orthanc Forwarder: when providing an instance_processor, you should have OverwriteInstances set to true to replace the instance with the new one")
                raise Exception("Invalid Orthanc configuration: OverwriteInstances is false")

    def execute(self):  # runs forever !
        self.wait_orthanc_started()

        while True:
            self.handle_all_content()
            time.sleep(self._polling_interval_in_seconds)

    def _process_resources(self, worker_id):
        logger.debug(f"Starting Forwarder thread {worker_id}")

        while True:
            try:
                resource = self._resources_to_process.get()  # block until a message is available

                if resource is None:  # sent by stop() to stop all worker threads
                    self._resources_to_process.task_done()
                    break

                if resource.type == "study":
                    self._handle_study(study_id=resource.resource_id,
                                       api_client=self._source)
                elif resource.type == "series":
                    self._handle_series(series_id=resource.resource_id,
                                        api_client=self._source)
                elif resource.type == "instance":
                    self._handle_instance(instance_id=resource.resource_id,
                                          api_client=self._source)

                self._resources_to_process.task_done()  # tell the queue the item has been processed

            except exceptions.ConnectionError as ex:
                logger.info(f"Connection error while handling {resource.type} {resource.resource_id}: {str(ex)}")
            except Exception as ex:
                logger.exception(f"Error while handling all {resource.type} {resource.resource_id}: {str(ex)}")

        logger.debug(f"Stopping Forwarder thread {worker_id}")

    def handle_all_content(self):
        # create worker threads
        for thread_id in range(0, self._worker_threads_count):
            self._worker_threads.append(threading.Thread(
                target=self._process_resources,
                name=f"Worker Thread {thread_id}",
                args=(thread_id,)
            ))

        # start threads
        for wt in self._worker_threads:
            wt.start()

        if self._trigger == ChangeType.STABLE_STUDY:
            studies_ids = self._source.studies.get_all_ids()
            if len(studies_ids) > 0:
                for study_id in studies_ids:
                    self._resources_to_process.put(ResourceToForward(type="study", resource_id=study_id))
            else:
                logger.debug("No studies found in Orthanc")

        elif self._trigger == ChangeType.STABLE_SERIES:
            series_ids = self._source.series.get_all_ids()
            if len(series_ids) > 0:
                for series_id in series_ids:
                    self._resources_to_process.put(ResourceToForward(type="series", resource_id=series_id))
            else:
                logger.debug("No series found in Orthanc")

        elif self._trigger == ChangeType.NEW_INSTANCE:
            instances_ids = self._source.instances.get_all_ids()
            if len(instances_ids) > 0:
                for instance_id in instances_ids:
                    self._resources_to_process.put(ResourceToForward(type="instance", resource_id=instance_id))
            else:
                logger.debug("No instances found in Orthanc")
        else:
            raise NotImplementedError()

        # post one 'empty' exit message per thread to unlock the threads from waiting on the process queue
        for i in range(0, self._worker_threads_count):
            self._resources_to_process.put(None)

        for t in self._worker_threads:
            t.join()

        self._worker_threads = []


    def _thread_execute(self):
        while self._is_running:
            self.handle_all_content()
            time.sleep(self._polling_interval_in_seconds)

    def start(self):
        logger.info("Starting Orthanc Forwarder")

        # create execution thread
        self._execution_thread = threading.Thread(
            target = self._thread_execute,
            name = 'OrthancForwarder execution thread'
        )

        self.wait_orthanc_started()

        # start threads
        self._is_running = True
        self._execution_thread.start()

    def stop(self):
        logger.info("Stopping Orthanc Forwarder")

        self._is_running = False
        self._execution_thread.join()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def _handle_study(self, study_id: str, api_client):
        if self._trigger == ChangeType.STABLE_STUDY and not self._is_study_stable(study_id, api_client):
            logger.debug(f"Study {study_id} is not stable yet")
            return

        instances_set = InstancesSet.from_study(api_client=api_client, study_id=study_id)
        self.handle_instances_set(instances_set)

    def _is_study_stable(self, study_id: str, api_client) -> bool:
        try:
            study = api_client.studies.get(study_id)
            return study.is_stable
        except ResourceNotFound:
            logger.debug(f"Study {study_id} disappeared before it could be handled")
            return False

    def _handle_series(self, series_id: str, api_client):
        instances_set = InstancesSet.from_series(api_client=api_client, series_id=series_id)
        self.handle_instances_set(instances_set)

    def _handle_instance(self, instance_id: str, api_client):
        instances_set = InstancesSet.from_instance(api_client=api_client, instance_id=instance_id)
        self.handle_instances_set(instances_set)

    def filter(self, instances_set: InstancesSet) -> InstancesSet:
        # this method can be overriden in a derived class.
        # By default, all instances not satisfying the filter are deleted
        if self._instance_filter:
            filtered = instances_set.filter_instances(self._instance_filter)
            logger.info(f"{instances_set} Deleting {len(filtered.instances_ids)} instances / {len(filtered.series_ids)} series that have been filtered out")
            filtered.delete()

        return instances_set

    def process(self, instances_set: InstancesSet) -> bool:
        # this method can be overriden in a derived class.

        if self._instance_processor:
            try:
                logger.info(f"{instances_set} Processing ...")

                instances_set.process_instances(self._instance_processor)

                logger.info(f"{instances_set} Processing ... done")
            except exceptions.OrthancApiException as ex:
                logger.error(f"{instances_set} Error while processing: {str(ex)}")
            except Exception as ex:
                logger.error(f"{instances_set} Error while processing: {str(ex)}", exc_info=True)
                return False

        return True

    def _schedule_retry(self, instances_set: InstancesSet, status: ForwarderInstancesSetStatus):
        retry_count = status.retry_count
        next_retry = datetime.datetime.now() + datetime.timedelta(
            seconds=self.retry_intervals[min(retry_count, len(self.retry_intervals) - 1)]
        )
        logger.info(f"{instances_set} Failed, will retry at {next_retry}")

        status.next_retry = next_retry
        status.retry_count = retry_count + 1

    def _mark_as_terminal(self, instances_set: InstancesSet, status: ForwarderInstancesSetStatus):
        logger.info(f"{instances_set} No eligible destinations matched; keeping source data")
        status.next_retry = None
        status.retry_count = 0
        status.terminal = True

    def forward(self, instances_set, already_sent_to_destinations: List[str]) -> Tuple[List[str], List[str]]:  # returns (sent destinations, eligible destinations)
        sent_to_destinations = list(already_sent_to_destinations)
        eligible_destinations = []
        log_context = self._get_cached_instances_set_log_context(instances_set)
        study_description = None
        study_description_loaded = False
        study_description_error = None

        # has_been_sent_to = self._status[instances_set.id].sent_to_destinations
        # check the metadata of a random instance to detect to which destinations it has already been sent (which would mean that we are retrying to process the set)
        #has_been_sent_to = self._source.instances.get_string_metadata(instances_set.instances_ids[0], metadata_name=str(ForwarderMetadata.SENT_TO_DESTINATIONS.value), default_value="").split(",")

        for dest in self._destinations:
            try:
                destination_retry_key = dest.retry_key
                if destination_retry_key in already_sent_to_destinations:
                    eligible_destinations.append(destination_retry_key)
                    logger.info(f"{instances_set} {log_context} Sending ... already sent to {dest.destination} using {dest.forwarder_mode}")
                    if self._on_instances_set_forwarded:
                        self._on_instances_set_forwarded(instances_set=instances_set,
                                                         destination=dest.destination)
                    continue

                if dest.study_description_match_type is not None:
                    if study_description_error is not None:
                        eligible_destinations.append(destination_retry_key)
                        raise study_description_error

                    if not study_description_loaded:
                        try:
                            study_description = self._get_study_description(instances_set)
                            study_description_loaded = True
                        except Exception as ex:
                            study_description_error = ex
                            eligible_destinations.append(destination_retry_key)
                            raise

                    if not dest.matches_study_description(study_description):
                        logger.info(
                            f"{instances_set} Skipping {dest.destination}: "
                            f"StudyDescription '{study_description or ''}' does not match "
                            f"{dest.study_description_match_type} filter '{dest.study_description_pattern}'"
                        )
                        continue

                eligible_destinations.append(destination_retry_key)
                logger.info(f"{instances_set} {log_context} Sending to {dest.destination} using {dest.forwarder_mode}")
                self._forward_to_destination(
                    instances_set=instances_set,
                    destination=dest
                )
                logger.info(f"{instances_set} {log_context} Sent")
                sent_to_destinations.append(destination_retry_key)

                if self._on_instances_set_forwarded:
                    self._on_instances_set_forwarded(instances_set=instances_set,
                                                     destination=dest.destination)

            except exceptions.OrthancApiException as ex:
                logger.error(f"{instances_set} {log_context} Error while forwarding to {dest.destination}: {ex.msg}")
                if self._on_instances_set_forward_error:
                    self._on_instances_set_forward_error(instances_set=instances_set,
                                                         destination=dest.destination,
                                                         error=ex.msg)
            except Exception as ex:
                logger.error(f"{instances_set} {log_context} Error while forwarding to {dest.destination}: {ex}", exc_info=True)
                if self._on_instances_set_forward_error:
                    self._on_instances_set_forward_error(instances_set=instances_set,
                                                         destination=dest.destination,
                                                         error=str(ex))

        return sent_to_destinations, eligible_destinations
            # has_been_sent_to = self._source.instances.get_string_metadata(instances_set.instances_ids[0], metadata_name=str(ForwarderMetadata.SENT_TO_DESTINATIONS.value), default_value="").split(",")


        # only save the sent_to_destinations if there are multiple destinations and there has been a failure.  Otherwise, we'll delete the data anyway right after
        # if len(self._destinations) > 1 and len(sent_to_destinations) > 1:
        #     self._set_string_metadata(instances_set, metadata_name=str(ForwarderMetadata.SENT_TO_DESTINATIONS.value), content=",".join(sent_to_destinations))
        # self._status[instances_set.id].sent_to_destinations = sent_to_destinations


    def delete(self, instances_set):
        log_context = self._get_cached_instances_set_log_context(instances_set)
        logger.info(f"{instances_set} {log_context} Deleting ...")
        del self._status[instances_set.id]
        instances_set.delete()
        logger.info(f"{instances_set} {log_context} Deleting ... Done")

    def handle_instances_set(self, instances_set: InstancesSet):

        if instances_set.id not in self._status:
            self._status[instances_set.id] = ForwarderInstancesSetStatus()
        status = self._status[instances_set.id]

        if status.terminal:
            logger.debug(f"{instances_set} Skipping permanently ineligible content")
            return

        if status.next_retry:  # this is a retry !
            if datetime.datetime.now() < status.next_retry:
                logger.debug(f"{instances_set} Skipping while waiting for retry")
                return

        log_context = self._get_cached_instances_set_log_context(instances_set)
        logger.info(f"{instances_set} {log_context} Handling ...")

        # filter
        instances_set = self.filter(instances_set)

        # process
        if not status.processed:
            status.processed = self.process(instances_set)
        else:
            logger.info(f"{instances_set} Skipping processing that has already been performed")

        # forward
        sent_to_destinations, eligible_destinations = self.forward(instances_set, status.sent_to_destinations)
        status.sent_to_destinations = sent_to_destinations
        status.last_eligible_destinations = eligible_destinations

        if len(eligible_destinations) == 0:
            self._mark_as_terminal(instances_set, status)
            return

        if len(sent_to_destinations) == len(eligible_destinations):
            # delete
            self.delete(instances_set)
        else:
            self._schedule_retry(instances_set, status)
            return

        logger.info(f"{instances_set} {log_context} Handling ... Done")

    def _forward_to_destination(self, instances_set: InstancesSet, destination: ForwarderDestination):
        if destination.forwarder_mode == ForwarderMode.DICOM:
            self._source.modalities.send(
                target_modality=destination.destination,
                resources_ids=instances_set.instances_ids
            )
        elif destination.forwarder_mode == ForwarderMode.DICOM_SERIES_BY_SERIES:
            for s in instances_set.series_ids:
                self._source.modalities.send(
                    target_modality=destination.destination,
                    resources_ids=instances_set.get_instances_ids(series_id=s)
                )
        elif destination.forwarder_mode == ForwarderMode.DICOM_WEB:
            for s in instances_set.series_ids:
                self._source.dicomweb_servers.send(
                    target_server=destination.destination,
                    resources_ids=instances_set.get_instances_ids(series_id=s)
                )
        elif destination.forwarder_mode == ForwarderMode.DICOM_WEB_SERIES_BY_SERIES:
            for s in instances_set.series_ids:
                series = self._source.series.get(s)
                if series.statistics.uncompressed_size > 1*1024*1024*1024:
                    logger.info(f"{instances_set} A series is larger than 1 GB, sending instance by instance")
                    for i in instances_set.get_instances_ids(series_id=s):
                        self._source.dicomweb_servers.send(
                            target_server=destination.destination,
                            resources_ids=[i]
                        )
                else:
                    self._source.dicomweb_servers.send(
                        target_server=destination.destination,
                        resources_ids=instances_set.get_instances_ids(series_id=s)
                    )
        elif destination.forwarder_mode == ForwarderMode.PEERING:
            self._source.peers.send(
                target_peer=destination.destination,
                resources_ids=instances_set.instances_ids
            )

        elif destination.forwarder_mode == ForwarderMode.TRANSFER:
            self._source.transfers.send(
                target_peer=destination.destination,
                resources_ids=instances_set.instances_ids,
                resource_type=ResourceType.INSTANCE
            )

        else:
            raise NotImplementedError

    def _get_instances_set_log_context(self, instances_set: InstancesSet) -> str:
        patient_id = self._get_patient_id(instances_set)
        sender_aet = self._get_sender_aet(instances_set)
        return f"PatientID={patient_id} SenderAET={sender_aet}"

    def _get_cached_instances_set_log_context(self, instances_set: InstancesSet) -> str:
        status = self._status.get(instances_set.id)
        if status is None:
            return self._get_instances_set_log_context(instances_set)

        if status.log_context is None:
            status.log_context = self._get_instances_set_log_context(instances_set)

        return status.log_context

    def _get_patient_id(self, instances_set: InstancesSet) -> str:
        try:
            study_id = self._get_study_id(instances_set)
            if not study_id:
                return UNKNOWN_LOG_CONTEXT_VALUE

            study = self._source.studies.get(study_id)
            patient_tags = getattr(study, 'patient_main_dicom_tags', None)
            if patient_tags is None and isinstance(study, dict):
                patient_tags = study.get('PatientMainDicomTags')

            if not patient_tags:
                return UNKNOWN_LOG_CONTEXT_VALUE

            return patient_tags.get('PatientID') or UNKNOWN_LOG_CONTEXT_VALUE
        except Exception as ex:
            logger.debug(f"{instances_set} Could not resolve PatientID for logs: {ex}")
            return UNKNOWN_LOG_CONTEXT_VALUE

    def _get_sender_aet(self, instances_set: InstancesSet) -> str:
        if len(instances_set.instances_ids) == 0:
            return UNKNOWN_LOG_CONTEXT_VALUE

        instance_id = instances_set.instances_ids[0]
        for metadata_name in REMOTE_AET_METADATA_NAMES:
            try:
                sender_aet = self._source.instances.get_string_metadata(
                    instance_id,
                    metadata_name=metadata_name,
                    default_value=None
                )
                if sender_aet:
                    return sender_aet
            except Exception as ex:
                logger.debug(f"{instances_set} Could not resolve {metadata_name} for logs: {ex}")

        return UNKNOWN_LOG_CONTEXT_VALUE

    def _get_study_id(self, instances_set: InstancesSet) -> Optional[str]:
        study_id = getattr(instances_set, 'study_id', None)
        if not study_id and len(instances_set.instances_ids) > 0:
            study_id = self._source.instances.get_parent_study_id(instances_set.instances_ids[0])

        return study_id

    def _get_study_description(self, instances_set: InstancesSet) -> Optional[str]:
        study_id = self._get_study_id(instances_set)
        if not study_id:
            return None

        study = self._source.studies.get(study_id)
        return study.main_dicom_tags.get('StudyDescription')

    def _set_string_metadata(self, instances_set: InstancesSet, metadata_name: str, content: str):
            instances_set.process_instances(lambda c, i: c.instances.set_string_metadata(
                orthanc_id=i,
                metadata_name=metadata_name,
                content=content
            ))

    def on_instances_set_forwarded(self, instances_set: InstancesSet, destination: str):
        pass

    def on_instances_set_forward_error(self, instances_set: InstancesSet, destination: str, error: str):
        pass


def add_parser_argument_w_alias(parser, name, *args, **kwargs):
    '''
    Add an argument to the parser with both the name and its alias 
    so that both `--source_url` and `--source-url` can be used.
    '''
    aliased = name.replace('_', '-')
    parser.add_argument(name, aliased, *args, **kwargs)


def build_forwarder_destination(entry: str, default_mode: ForwarderMode) -> ForwarderDestination:
    destination_spec = entry.strip()
    if not destination_spec:
        raise ValueError("Destination entries cannot be blank.")

    parts = destination_spec.split(":", 3)
    destination_name = parts[0].strip()
    if not destination_name:
        raise ValueError(f"Destination alias is missing in '{destination_spec}'.")

    destination_mode = default_mode
    if len(parts) > 1 and parts[1].strip():
        destination_mode = _parse_mode(parts[1].strip(), f"destination '{destination_name}'")

    study_description_match_type = None
    study_description_pattern = None

    if len(parts) > 2:
        match_type_part = parts[2].strip().lower()
        if not match_type_part:
            raise ValueError(
                f"StudyDescription match type is missing for destination '{destination_name}' in '{destination_spec}'."
            )

        valid_match_types = {m.value for m in StudyDescriptionMatchType}
        if match_type_part not in valid_match_types:
            raise ValueError(
                f"Invalid StudyDescription match type '{parts[2]}' for destination '{destination_name}'. "
                f"Allowed values: {sorted(valid_match_types)}"
            )

        if len(parts) < 4 or not parts[3].strip():
            raise ValueError(
                f"StudyDescription filter pattern is missing for destination '{destination_name}' in '{destination_spec}'."
            )

        study_description_match_type = StudyDescriptionMatchType(match_type_part)
        study_description_pattern = parts[3].strip()

    return ForwarderDestination(
        destination=destination_name,
        forwarder_mode=destination_mode,
        study_description_match_type=study_description_match_type,
        study_description_pattern=study_description_pattern
    )


def parse_forwarder_destinations(raw_destinations: List[str], default_mode: ForwarderMode) -> List[ForwarderDestination]:
    return [build_forwarder_destination(dest, default_mode) for dest in raw_destinations]


def split_destination_entries(raw_value: str) -> List[str]:
    if not raw_value:
        return []

    reader = csv.reader([raw_value], skipinitialspace=True)
    return [entry.strip() for entry in next(reader) if entry.strip()]


def split_cli_destination_entries(raw_values: List[str]) -> List[str]:
    raw_destinations = []
    for raw_value in raw_values:
        raw_destinations.extend(split_destination_entries(raw_value))
    return raw_destinations


def _parse_mode(mode_value: str, context: str) -> ForwarderMode:
    normalized = mode_value.lower()
    valid_modes = {m.value for m in ForwarderMode}
    if normalized not in valid_modes:
        raise ValueError(f"Invalid mode '{mode_value}' for {context}. Allowed modes: {sorted(valid_modes)}")
    return ForwarderMode(normalized)

if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    valid_modes = {m.value for m in ForwarderMode}

    parser = argparse.ArgumentParser(description='Forwards everything Orthanc receives to another Orthanc peer, a DICOM modality or DicomWeb server.')

    add_parser_argument_w_alias(parser, '--source_url', type=str, default=None, help='Orthanc source url')
    add_parser_argument_w_alias(parser, '--source_user', type=str, default=None, help='Orthanc source user name')
    add_parser_argument_w_alias(parser, '--source_pwd', type=str, default=None, help='Orthanc source password')
    add_parser_argument_w_alias(parser, '--source_api_key', type=str, default=None, help='Orthanc source api-key')
    add_parser_argument_w_alias(
        parser,
        '--destination',
        type=str,
        action='append',
        default=[],
        help='Destination alias with optional mode override and StudyDescription filter '
             '(alias[:mode[:substring:pattern|:regex:pattern]]). Repeat flag to add multiple destinations.'
    )
    add_parser_argument_w_alias(parser, '--worker_threads_count', type=int, default=1, help='Number of worker threads')
    add_parser_argument_w_alias(parser, '--polling_interval', type=int, default=1, help='Polling interval (in seconds)')
    add_parser_argument_w_alias(parser, '--trigger', type=str, default=None, help='NewInstance or StableStudy')
    add_parser_argument_w_alias(parser, '--mode', type=str, default='dicom', help=f'Default forwarder mode. One of: {", ".join(sorted(valid_modes))}')

    args = parser.parse_args()

    source_url = os.environ.get("SOURCE_URL", args.source_url)
    source_user = os.environ.get("SOURCE_USER", args.source_user)
    source_pwd = os.environ.get("SOURCE_PWD", args.source_pwd)
    source_api_key = os.environ.get("SOURCE_API_KEY", args.source_api_key)
    destinations_env = os.environ.get("DESTINATIONS")
    destination_env = os.environ.get("DESTINATION")
    dest_from_args = args.destination or []
    raw_destinations = []

    if destinations_env:
        raw_destinations = split_destination_entries(destinations_env)
    elif destination_env:
        raw_destinations = [destination_env.strip()]
    elif dest_from_args:
        raw_destinations = split_cli_destination_entries(dest_from_args)

    if not raw_destinations:
        raise ValueError("At least one destination must be provided via --destination, DESTINATION, or DESTINATIONS.")
    worker_threads_count = int(os.environ.get("WORKER_THREADS_COUNT", str(args.worker_threads_count)))
    polling_interval_in_seconds = int(os.environ.get("POLLING_INTERVAL", str(args.polling_interval)))
    trigger = os.environ.get("TRIGGER", args.trigger)
    mode_str = os.environ.get("MODE", args.mode)

    # Validate trigger
    if trigger == "StableStudy":
        trigger = ChangeType.STABLE_STUDY
    elif trigger == "NewInstance":
        trigger = ChangeType.NEW_INSTANCE
    else:
        raise ValueError("Trigger parameter not valid!")

    # Validate default mode
    chosen_mode = _parse_mode(mode_str, "default mode (--mode/MODE)")

    # Create API client
    if source_api_key is not None:
        api_client = OrthancApiClient(source_url, headers={"api-key": source_api_key}, pool_maxsize=max(10, worker_threads_count), pool_block=True)
    else:
        api_client = OrthancApiClient(source_url, user=source_user, pwd=source_pwd, pool_maxsize=max(10, worker_threads_count), pool_block=True)

    forwarder_destinations = parse_forwarder_destinations(raw_destinations, chosen_mode)

    forwarder = OrthancForwarder(
        source=api_client,
        destinations=forwarder_destinations,
        trigger=trigger,
        worker_threads_count=worker_threads_count,
        polling_interval_in_seconds=polling_interval_in_seconds
    )

    forwarder.execute()
