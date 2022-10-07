import queue
import threading
import time
import os
import logging
import argparse
import datetime
import multiprocessing
import random
import pydicom
import uuid
from orthanc_api_client import helpers
from .scheduler import Scheduler

from orthanc_api_client import OrthancApiClient
logger = logging.getLogger('orthanc_tools')


class Message:
    def __init__(self, dicom_id: str = None, orthanc_id: str = None, should_stop: bool = False):
        self.dicom_id = dicom_id
        self.orthanc_id = orthanc_id
        self.should_stop = should_stop


class PacsMigrator:
    """
    Migrates DICOM studies from a SOURCE modality (usually a PACS) to another DESTINATION modality (usually Orthanc).
    The migrator must be attached to an Orthanc which can be the SOURCE or the DESTINATION

    There are multiple use cases to use this class:
    - as the SOURCE
      MIGRATOR --> DESTINATION
      To work in this setup, you must provide:
      - the destination_modality (defined in the MIGRATOR config)
      - you may optionally delete the images from the source afterward

    - as a passive intermediate between the source and destination.  This is useful to transfer images between the source and destination without modifying them.
      SOURCE --> DESTINATION
         |
      MIGRATOR
      To work in this setup, you must provide:
      - the source_modality (Orthanc alias defined in the MIGRATOR config)
      - the destination_aet (no need to define it in the MIGRATOR config)
      - set destination_modality to None

    - to populate Orthanc from a remote modality (in this case, the MIGRATOR is the target)
      SOURCE --> MIGRATOR
      To work in this setup, you must provide:
      - the source_modality (Orthanc alias defined in the MIGRATOR config)
      - set destination_modality to None
      - set destination_aet to None

    """

    def __init__(self,
                 api_client: OrthancApiClient,
                 from_study_date: datetime.date,        # Start date
                 to_study_date: datetime.date,          # End date
                 source_modality: str = None,           # Source modality as configured in Orthanc (alias)
                 max_cfind_study_count: int = None,     # Known maximum amount of studies retrievable from the source modality at once
                 destination_modality: str = None,      # Destination modality as configured in Orthanc (alias)
                 destination_aet: str = None,           # Destination AET
                 delete_from_source: bool = False,      # once the data has been migrated, delete it from source (only vali
                 scheduler: Scheduler = None,
                 worker_threads_count: int = multiprocessing.cpu_count() - 1  # by default, use all CPUs but one for compression
                 ):

        if (destination_aet is not None and destination_modality is not None):
            raise ValueError("You cannot define destinationAet and destinationModality together")

        self._api_client = api_client
        self._source_modality = source_modality
        self._from_study_date = from_study_date
        self._to_study_date = to_study_date
        self._max_cfind_study_count = max_cfind_study_count
        self._destination_modality = destination_modality
        self._destination_aet = destination_aet
        self._delete_from_source = delete_from_source
        self._scheduler = scheduler

        self._worker_threads_count = worker_threads_count
        self._worker_threads = []
        self._messages = queue.Queue(maxsize=2*worker_threads_count)  # this is thread safe https://docs.python.org/3.5/library/queue.html#module-queue
        self._is_running = False

        self._dicom_tags_to_query = {  # this might be extended once we implement filters
            'AccessionNumber': '',
            'PatientName': '',
            'StudyInstanceUID': ''
        }

        if not self._destination_modality and not self._destination_aet:
            # destination is orthanc -> set orthanc AET
            self._destination_aet = self._api_client.get_json('/system')["DicomAet"]

    @property
    def source_is_orthanc(self):
        return self._source_modality is None

    @property
    def target_is_orthanc(self):
        return self._destination_aet is None and self._destination_modality is None

    def process_messages(self, worker_thread_id: int):
        logger.debug(f"Starting Processing thread {worker_thread_id}")

        while True:
            message = self._messages.get()  # block until a message is available

            if message.should_stop:  # sent by stop() to stop all worker threads
                self._messages.task_done()
                break

            if self.source_is_orthanc:
                try:
                    logger.info(f"C-Store study {message.orthanc_id} from orthanc to destination modality {self._destination_modality}")
                    # move the study from orthanc to the target modality
                    self._api_client.modalities.send(
                        target_modality=self._destination_modality,
                        resources_ids=message.orthanc_id,
                        synchronous=True
                    )

                    if self._delete_from_source:
                        self._api_client.studies.delete(
                            orthanc_id=message.orthanc_id
                        )
                except Exception as ex:
                    logger.error(f"Error while transferring {message.orthanc_id} {str(ex)}")


            elif self._source_modality and self._destination_aet:
                retry_count = 0
                while retry_count < 5:
                    try:
                        logger.info(f"C-Move study {message.dicom_id} from source {self._source_modality} to destination AET {self._destination_aet}")
                        # move the study from source to target modality
                        self._api_client.modalities.move_study(
                            from_modality=self._source_modality,
                            dicom_id=message.dicom_id,
                            to_modality_aet=self._destination_aet
                        )
                        break
                    except Exception as ex:
                        retry_count += 1
                        if retry_count == 5:
                            logger.error(f"Error (retried 5 times) while transferring {message.dicom_id} {str(ex)}")
                        else:
                            logger.warning(f"Error while transferring, retrying... {message.dicom_id} {str(ex)}")

            else:
                raise NotImplementedError("configuration not handled")

            self._messages.task_done()  # tell the queue the item has been processed

        logger.debug(f"Processing thread {worker_thread_id} stopped")

    def push_message(self, message: Message):
        if self._scheduler:
            self._scheduler.wait_right_time_to_run(logger=logger)

        self._messages.put(message)


    def execute(self):
        if self._is_running:
            raise RuntimeError("Migrator is already running")

        if self._source_modality:
            logger.info("From Modality: " + self._source_modality)
        if self._destination_aet:
            logger.info("To AET: " + self._destination_aet)
        elif self._destination_modality:
            logger.info("To Modality: " + self._destination_modality)
        else:
            logger.info("To itself")

        logger.info("From Date: " + str(self._from_study_date))
        logger.info("To Date  : " + str(self._to_study_date))

        if self._scheduler:
            logger.info("Night & Week-end mode Enabled : " + str(self._scheduler._run_only_at_night_and_weekend))

        logger.info("Migrating with {n} threads".format(n = self._worker_threads_count))

        # create worker threads
        for i in range(0, self._worker_threads_count):
            self._worker_threads.append(threading.Thread(
                target=self.process_messages,
                name=f'Worker Thread {i}',
                args=(i,)
            ))

        # start threads
        self._is_running = True
        for worker_thread in self._worker_threads:
            worker_thread.start()

        if self._from_study_date < self._to_study_date:
            # ex 20220101 -> 20220131
            inc_date = 1
            to_date = self._to_study_date + datetime.timedelta(days=1)
        else:
            # ex 20220131 -> 20220101
            inc_date = -1
            to_date = self._to_study_date - datetime.timedelta(days=1)

        current_date = self._from_study_date

        while current_date != to_date:
            logger.info("Processing date {date}".format(date=str(current_date)))

            query = self._dicom_tags_to_query
            query["StudyDate"] = helpers.to_dicom_date(current_date)

            if self.source_is_orthanc:
                logger.info("Querying Orthanc")
                local_studies = self._api_client.studies.find(query=query)

                logger.info(f"Found {len(local_studies)} studies")

                for study in local_studies:
                    self.push_message(Message(orthanc_id=study.orthanc_id))
            else:
                logger.info(f"Querying remote modality {self._source_modality}")

                retry_count = 0
                while retry_count < 5:
                    try:
                        remote_modality_studies = self._api_client.modalities.query_studies(
                            from_modality=self._source_modality,
                            query=query
                        )
                        break

                    except Exception as ex:
                        retry_count += 1
                        if retry_count == 5:
                            logger.error("Could not query the modality (retried 5 times), aborting")
                            return

                logger.info(f"Found {len(remote_modality_studies)} studies")

                if self._max_cfind_study_count and len(remote_modality_studies) == self._max_cfind_study_count:
                    logger.error(f"Too many studies in a single request: {len(remote_modality_studies)}, you'll probably miss some studies")

                for study in remote_modality_studies:
                    self.push_message(Message(dicom_id=study.dicom_id))

            current_date += datetime.timedelta(days=inc_date)

        logger.info("Waiting for worker threads to complete")
        # post one 'empty' exit message per thread to unlock the threads from waiting on the process queue
        for i in range(0, self._worker_threads_count):
            self._messages.put(Message(should_stop=True))

        for worker_thread in self._worker_threads:
            worker_thread.join()

        self._is_running = False
        self._worker_threads = []

        logger.info("--------------------------------------------------------------------")
        logger.info("Migration completed")


# examples:
# migrator as source: MIGRATOR --> DESTINATION:  ! use the --delete_from_source option with care !!!
# python orthanc_tools/pacs_migrator.py --url=http://localhost:8042 --user=user --password=pwd --destination_modality=orthanc-debug --from_study_date=20000101 --to_study_date=20191231 --run_only_at_night_and_weekend --night_start_hour=18 --night_end_hour=6
#
#
# migrator aside from source and destination:
# SOURCE --> DESTINATION
#   |
# MIGRATOR
# python orthanc_tools/pacs_migrator.py --url=http://localhost:8044 --user=user --password=pwd --source_modality=service --destination_aet=ORTHANC --from_study_date=20000101 --to_study_date=20191231 --run_only_at_night_and_weekend --night_start_hour=18 --night_end_hour=6
#
#
# migrator as the destination: SOURCE --> MIGRATOR:
# python orthanc_tools/pacs_migrator.py --url=http://localhost:8044 --user=user --password=pwd --source_modality=service --destination_aet=ORTHANC-DEBUG --from_study_date=20000101 --to_study_date=20191231 --run_only_at_night_and_weekend --night_start_hour=18 --night_end_hour=6
#



if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Migrate the content of a remote modality to another modality')
    parser.add_argument('--url', type=str, default=None, help='Orthanc url (migrator)')
    parser.add_argument('--user', type=str, default=None, help='Orthanc user name')
    parser.add_argument('--password', type=str, default=None, help='Orthanc password')
    parser.add_argument('--destination_modality', type=str, default=None, help='Destination modality (alias)')
    parser.add_argument('--destination_aet', type=str, default=None, help='Destination AET')
    parser.add_argument('--source_modality', type=str, default=None, help='Source modality (alias)')
    parser.add_argument('--from_study_date', type=str, required=True, help='From Study Date (format 20190225)')
    parser.add_argument('--to_study_date', type=str, required=True, help='To Study Date (format 20190225)')
    parser.add_argument('--delete_from_source', default=False, action='store_true', help='delete data from source (only if source is an Orthanc)')
    parser.add_argument('--worker_threads_count', type=int, default=1, help='Worker threads count')
    Scheduler.add_parser_arguments(parser)

    args = parser.parse_args()

    url = os.environ.get("ORTHANC_URL", args.url)
    user = os.environ.get("ORTHANC_USER", args.user)
    pwd = os.environ.get("ORTHANC_PWD", args.password)
    destination_modality = os.environ.get("DESTINATION_MODALITY", args.destination_modality)
    destination_aet = os.environ.get("DESTINATION_AET", args.destination_aet)
    source_modality = os.environ.get("SOURCE_MODALITY", args.source_modality)
    from_study_date = helpers.from_dicom_date(os.environ.get("FROM_STUDY_DATE", args.from_study_date))
    to_study_date = helpers.from_dicom_date(os.environ.get("TO_STUDY_DATE", args.to_study_date))
    worker_threads_count = int(os.environ.get("WORKER_THREADS_COUNT", str(args.worker_threads_count)))

    scheduler = Scheduler.create_from_args_and_env_var(args)

    if os.environ.get("DELETE_FROM_SOURCE", None) is not None:
        delete_from_source = os.environ.get("DELETE_FROM_SOURCE") == "true"
    else:
        delete_from_source = args.delete_from_source

    migrator = PacsMigrator(
        api_client=OrthancApiClient(url, user=user, pwd=pwd),
        from_study_date=from_study_date,
        to_study_date=to_study_date,
        destination_modality=destination_modality,
        destination_aet=destination_aet,
        source_modality=source_modality,
        delete_from_source=delete_from_source,
        scheduler=scheduler,
        worker_threads_count=worker_threads_count
    )

    migrator.execute()
