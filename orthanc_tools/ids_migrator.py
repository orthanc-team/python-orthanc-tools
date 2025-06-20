import pprint
import sys
import os
import logging
import argparse
import datetime
import multiprocessing
from orthanc_api_client import helpers
from .helpers.scheduler import Scheduler
from .dicom_migrator import DicomMigrator, Message
import csv

from orthanc_api_client import OrthancApiClient
logger = logging.getLogger(__name__)

class IdsMigrator(DicomMigrator):
    """
    Uses the DicomMigrator to migrate a list of studies based on a csv file containing the UIDs.
    """

    def __init__(self,
                 api_client: OrthancApiClient,
                 ids_list_file_path: str,               # Path of the file containing the ids of the studies to migrate
                 source_modality: str = None,           # Source modality as configured in Orthanc (alias)
                 max_cfind_study_count: int = None,     # Known maximum amount of studies retrievable from the source modality at once
                 destination_modality: str = None,      # Destination modality as configured in Orthanc (alias)
                 destination_aet: str = None,           # Destination AET
                 delete_from_source: bool = False,      # once the data has been migrated, delete it from source (only vali
                 scheduler: Scheduler = None,
                 worker_threads_count: int = multiprocessing.cpu_count() - 1,  # by default, use all CPUs but one for compression
                 exit_on_error: bool = False,
                 use_get_not_move: bool = False
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
            use_get_not_move=use_get_not_move
        )

        self._ids_list_file_path = ids_list_file_path

    def execute(self):
        super().execute()

        logger.info("Path of the file containing the ids of the studies to migrate: " + str(self._ids_list_file_path))

        # The input could be a simple text file, each line being an id but also the output of another script with more
        # information, so we take the first item of each line
        ids_list = []
        with open(self._ids_list_file_path, 'r') as csv_file:
            reader = csv.reader(csv_file)
            for line in reader:
                ids_list.append(line[0])

        for id in ids_list:
            logger.info(f"Processing id {id}")
            self.push_message(Message(dicom_id=id))

        self.stop_threads()

        logger.info("--------------------------------------------------------------------")
        logger.info("Migration completed")


# examples:
# migrator as source: MIGRATOR --> DESTINATION:  ! use the --delete_from_source option with care !!!
# python orthanc_tools/ids_migrator.py --url=http://localhost:8042 --user=user --password=pwd --destination_modality=orthanc-debug --ids_list_file_path=/ids_list.csv --run_only_at_night_and_weekend --night_start_hour=18 --night_end_hour=6


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
    parser.add_argument('--ids_list_file_path', type=str,  required='IDS_LIST_FILE_PATH' not in os.environ, help='Path of the file containing the ids of the studies to migrate')
    parser.add_argument('--delete_from_source', default=False, action='store_true', help='delete data from source (only if source is an Orthanc)')
    parser.add_argument('--worker_threads_count', type=int, default=1, help='Worker threads count')
    parser.add_argument('--exit_on_error', default=False, action='store_true', help='if True, the script will exit in case of error')
    parser.add_argument('--use_get_not_move', default=False, action='store_true', help='use a C-Get in place of C-Move (only if destination is Orthanc)')

    Scheduler.add_parser_arguments(parser)

    args = parser.parse_args()

    url = os.environ.get("ORTHANC_URL", args.url)
    user = os.environ.get("ORTHANC_USER", args.user)
    pwd = os.environ.get("ORTHANC_PWD", args.password)
    destination_modality = os.environ.get("DESTINATION_MODALITY", args.destination_modality)
    destination_aet = os.environ.get("DESTINATION_AET", args.destination_aet)
    source_modality = os.environ.get("SOURCE_MODALITY", args.source_modality)
    ids_list_file_path = os.environ.get("IDS_LIST_FILE_PATH", args.ids_list_file_path)
    worker_threads_count = int(os.environ.get("WORKER_THREADS_COUNT", str(args.worker_threads_count)))

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

    migrator = IdsMigrator(
        api_client=OrthancApiClient(url, user=user, pwd=pwd),
        ids_list_file_path=ids_list_file_path,
        destination_modality=destination_modality,
        destination_aet=destination_aet,
        source_modality=source_modality,
        delete_from_source=delete_from_source,
        scheduler=scheduler,
        worker_threads_count=worker_threads_count,
        exit_on_error=exit_on_error,
        use_get_not_move=use_get_not_move
    )

    migrator.execute()
