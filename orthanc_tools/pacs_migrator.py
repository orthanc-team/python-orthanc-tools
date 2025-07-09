import queue
import sys
import threading
import time
import os
import logging
import argparse
import datetime
import multiprocessing
from orthanc_api_client import helpers
from .helpers.scheduler import Scheduler
from .dicom_migrator import DicomMigrator, Message

from orthanc_api_client import OrthancApiClient
logger = logging.getLogger(__name__)

class PacsMigrator(DicomMigrator):
    """
    Uses the DicomMigrator to migrate a range of dates.
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
                 worker_threads_count: int = multiprocessing.cpu_count() - 1,  # by default, use all CPUs but one for compression
                 exit_on_error: bool = False,
                 orthanc_space_threshold: int = 0,
                 waiting_time_for_space_threshold: int = 600, # useful for unit tests
                 use_get_not_move: bool = False,
                 max_retries: int = 5,
                 constant_retry_delays: bool = False
                 ):

        super().__init__(
            api_client=api_client,
            source_modality=source_modality,
            max_cfind_study_count=max_cfind_study_count,
            destination_modality=destination_modality,
            destination_aet=destination_aet,
            delete_from_source=delete_from_source,
            scheduler=scheduler,
            worker_threads_count=worker_threads_count,
            exit_on_error=exit_on_error,
            use_get_not_move=use_get_not_move,
            max_retries=max_retries,
            constant_retry_delays=constant_retry_delays
        )

        self._from_study_date = from_study_date
        self._to_study_date = to_study_date
        self._orthanc_space_threshold = orthanc_space_threshold
        self._waiting_time_for_space_threshold = waiting_time_for_space_threshold

    def wait_for_space_in_orthanc(self):
        '''
        At some point, we need to migrate a local PACS to a cloud Orthanc.
        To do that, we use current class, with an Orthanc which is also a dicomweb-forwarder.
        The problem is that the transfer from the local DICOM PACS to the forwarder is faster
        than the transfer from the forwarder to the cloud Orthanc.
        And so, the local server HD is full.
        
        Goal of this method: wait until the disk space used by Orthanc is above a threshold.
        '''

        total_disk_size_mb = self._api_client.get_statistics().total_disk_size_mb
        while total_disk_size_mb > self._orthanc_space_threshold:
            logger.info(f"Wait {self._waiting_time_for_space_threshold}s until Orthanc disk space used ({total_disk_size_mb}MB) is lower than {self._orthanc_space_threshold}MB")
            time.sleep(self._waiting_time_for_space_threshold)
            total_disk_size_mb = self._api_client.get_statistics().total_disk_size_mb

    def execute(self):
        super().execute()

        logger.info("From Date: " + str(self._from_study_date))
        logger.info("To Date  : " + str(self._to_study_date))

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
                if self._orthanc_space_threshold > 0:
                    self.wait_for_space_in_orthanc()

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
                            if self._exit_on_error:
                                logger.info("exiting due to an error...")
                                self.stop_threads()
                                sys.exit(1)
                            return

                logger.info(f"Found {len(remote_modality_studies)} studies")

                if self._max_cfind_study_count and len(remote_modality_studies) == self._max_cfind_study_count:
                    logger.error(f"Too many studies in a single request: {len(remote_modality_studies)}, you'll probably miss some studies")
                    if self._exit_on_error:
                        logger.info("exiting due to an error...")
                        self.stop_threads()
                        sys.exit(1)

                for study in remote_modality_studies:
                    self.push_message(Message(dicom_id=study.dicom_id))

            current_date += datetime.timedelta(days=inc_date)

        self.stop_threads()

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
    parser.add_argument('--api_key', type=str, default=None, help='Orthanc api-key')
    parser.add_argument('--destination_modality', type=str, default=None, help='Destination modality (alias)')
    parser.add_argument('--destination_aet', type=str, default=None, help='Destination AET')
    parser.add_argument('--source_modality', type=str, default=None, help='Source modality (alias)')
    parser.add_argument('--from_study_date', type=str, required='FROM_STUDY_DATE' not in os.environ, help='From Study Date (format 20190225)')
    parser.add_argument('--to_study_date', type=str, required='TO_STUDY_DATE' not in os.environ, help='To Study Date (format 20190225)')
    parser.add_argument('--delete_from_source', default=False, action='store_true', help='delete data from source (only if source is an Orthanc)')
    parser.add_argument('--worker_threads_count', type=int, default=1, help='Worker threads count')
    parser.add_argument('--exit_on_error', default=False, action='store_true', help='if True, the script will exit in case of error')
    parser.add_argument('--orthanc_space_threshold', type=int, default=0, help='[MB] If different from 0, Migrator will wait until disk space used by Orthanc is above this value.')
    parser.add_argument('--use_get_not_move', default=False, action='store_true', help='use a C-Get in place of C-Move (only if destination is Orthanc)')
    parser.add_argument('--max_retries', type=int, default=5, help='Maximum number of retries')
    parser.add_argument('--constant_retry_delays', default=False, action='store_true', help='Use constant 60 seconds retry instead of the default increasing delay retries')

    Scheduler.add_parser_arguments(parser)

    args = parser.parse_args()

    url = os.environ.get("ORTHANC_URL", args.url)
    user = os.environ.get("ORTHANC_USER", args.user)
    pwd = os.environ.get("ORTHANC_PWD", args.password)
    api_key = os.environ.get("ORTHANC_API_KEY", args.api_key)
    destination_modality = os.environ.get("DESTINATION_MODALITY", args.destination_modality)
    destination_aet = os.environ.get("DESTINATION_AET", args.destination_aet)
    source_modality = os.environ.get("SOURCE_MODALITY", args.source_modality)
    from_study_date = helpers.from_dicom_date(os.environ.get("FROM_STUDY_DATE", args.from_study_date))
    to_study_date = helpers.from_dicom_date(os.environ.get("TO_STUDY_DATE", args.to_study_date))
    worker_threads_count = int(os.environ.get("WORKER_THREADS_COUNT", str(args.worker_threads_count)))
    orthanc_space_threshold = int(os.environ.get("ORTHANC_SPACE_THRESHOLD", str(args.orthanc_space_threshold)))
    max_retries = int(os.environ.get("MAX_RETRIES", str(args.max_retries)))

    if os.environ.get("USE_GET_NOT_MOVE", None) is not None:
        use_get_not_move = os.environ.get("USE_GET_NOT_MOVE") in ["true", "True"]
    else:
        use_get_not_move = args.use_get_not_move

    scheduler = Scheduler.create_from_args_and_env_var(args)

    if os.environ.get("DELETE_FROM_SOURCE", None) is not None:
        delete_from_source = os.environ.get("DELETE_FROM_SOURCE") == "true"
    else:
        delete_from_source = args.delete_from_source

    if os.environ.get("EXIT_ON_ERROR", None) is not None:
        exit_on_error = os.environ.get("EXIT_ON_ERROR") == "true"
    else:
        exit_on_error = args.exit_on_error

    if os.environ.get("CONSTANT_RETRY_DELAYS", None) is not None:
        constant_retry_delays = os.environ.get("CONSTANT_RETRY_DELAYS") in ["true", "True"]
    else:
        constant_retry_delays = args.constant_retry_delays

    api_client = None
    if api_key is not None:
        api_client=OrthancApiClient(url, headers={"api-key":api_key})
    else:
        api_client=OrthancApiClient(url, user=user, pwd=pwd)

    migrator = PacsMigrator(
        api_client=api_client,
        from_study_date=from_study_date,
        to_study_date=to_study_date,
        destination_modality=destination_modality,
        destination_aet=destination_aet,
        source_modality=source_modality,
        delete_from_source=delete_from_source,
        scheduler=scheduler,
        worker_threads_count=worker_threads_count,
        exit_on_error=exit_on_error,
        orthanc_space_threshold=orthanc_space_threshold,
        use_get_not_move=use_get_not_move,
        max_retries=max_retries,
        constant_retry_delays=constant_retry_delays
    )

    migrator.execute()
