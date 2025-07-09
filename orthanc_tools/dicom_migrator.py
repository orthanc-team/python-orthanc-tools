import queue
import sys
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
from .helpers.scheduler import Scheduler

from orthanc_api_client import OrthancApiClient
logger = logging.getLogger(__name__)


class Message:
    def __init__(self, dicom_id: str = None, orthanc_id: str = None, should_stop: bool = False):
        self.dicom_id = dicom_id
        self.orthanc_id = orthanc_id
        self.should_stop = should_stop


class DicomMigrator:
    """
    ********************************************************************
    *** This class shouldn't be used at it is, it has to be derived. ***
    ********************************************************************

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
                 source_modality: str = None,           # Source modality as configured in Orthanc (alias)
                 max_cfind_study_count: int = None,     # Known maximum amount of studies retrievable from the source modality at once
                 destination_modality: str = None,      # Destination modality as configured in Orthanc (alias)
                 destination_aet: str = None,           # Destination AET
                 delete_from_source: bool = False,      # once the data has been migrated, delete it from source (only vali
                 scheduler: Scheduler = None,
                 worker_threads_count: int = multiprocessing.cpu_count() - 1,  # by default, use all CPUs but one for compression
                 exit_on_error: bool = False,
                 use_get_not_move: bool = False,
                 max_retries: int = 5,
                 constant_retry_delays: bool = False
                 ):

        if (destination_aet is not None and destination_modality is not None):
            raise ValueError("You cannot define destinationAet and destinationModality together")

        self._api_client = api_client
        self._source_modality = source_modality
        self._max_cfind_study_count = max_cfind_study_count
        self._destination_modality = destination_modality
        self._destination_aet = destination_aet
        self._delete_from_source = delete_from_source
        self._scheduler = scheduler
        self._exit_on_error = exit_on_error
        self._use_get_not_move = use_get_not_move
        self._max_retries = max_retries
        self._constant_retry_delays = constant_retry_delays
        
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
            self._destination_aet = self._api_client.get_json('system')["DicomAet"]

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
                        resources_ids=message.orthanc_id
                    )

                    if self._delete_from_source:
                        self._api_client.studies.delete(
                            orthanc_id=message.orthanc_id
                        )
                except Exception as ex:
                    logger.error(f"Error while transferring {message.orthanc_id} {str(ex)}")
                    if self._exit_on_error:
                        logger.info("exiting due to an error...")
                        self.stop_threads()
                        sys.exit(1)


            elif self._source_modality and self._destination_aet:
                retry_count = 0
                if self._constant_retry_delays:
                    retry_delays = [60]
                else:
                    retry_delays = [5, 20, 60, 120, 300, 600, 900, 1200, 1500, 1800, 3600]

                while retry_count < self._max_retries:
                    if retry_count >= 1:
                        delay = retry_delays[min(retry_count, retry_delays) - 1]
                        logger.info(f"waiting {delay} seconds before retrying C-Move for study {message.dicom_id}")
                        time.sleep(delay)

                    try:
                        # not possible to use the `retrive_study` method because the destination could be something else than Orthanc
                        if self._use_get_not_move:
                            logger.info(
                                f"C-Get study {message.dicom_id} from source {self._source_modality} to Orthanc ({self._destination_aet})")
                            # get the study from source to Orthanc
                            self._api_client.modalities.get_study(
                                from_modality=self._source_modality,
                                dicom_id=message.dicom_id
                            )
                            break
                        else:
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
                            if self._exit_on_error:
                                logger.info("exiting due to an error...")
                                self.stop_threads()
                                sys.exit(1)
                        else:
                            logger.warning(f"Error while transferring, retrying... {message.dicom_id} {str(ex)}")

            else:
                raise NotImplementedError("configuration not handled")

            self._messages.task_done()  # tell the queue the item has been processed

        logger.debug(f"Processing thread {worker_thread_id} stopped")

    def push_message(self, message: Message):
        if self._scheduler:
            self._scheduler.wait_right_time_to_run()

        self._messages.put(message)

    def stop_threads(self):
        logger.info("Waiting for worker threads to complete")
        # post one 'empty' exit message per thread to unlock the threads from waiting on the process queue
        for i in range(0, self._worker_threads_count):
            self._messages.put(Message(should_stop=True))

        for worker_thread in self._worker_threads:
            worker_thread.join()

        self._is_running = False
        self._worker_threads = []

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

        if self._scheduler:
            logger.info("Night & Week-end mode Enabled : " + str(self._scheduler._run_only_at_night_and_weekend))

        logger.info("Migrating with {n} threads".format(n=self._worker_threads_count))

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


