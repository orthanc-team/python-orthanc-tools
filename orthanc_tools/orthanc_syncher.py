import os, time
import logging
import argparse
import tempfile
import datetime
from typing import List

from .helpers.scheduler import Scheduler
from orthanc_api_client import helpers
import logging
from orthanc_api_client import OrthancApiClient
import schedule

logger = logging.getLogger(__name__)

class OrthancSyncher:
    '''
    ## Goal
    The Syncher will ensure that all the studies/series/instances stored in Orthanc-1 are also
    stored in Orthanc-2 (and vice-versa).

    ## Context
    The modalities are configured to send the images to both Orthanc-1 and Orthanc-2, so that,
    if one of the 2 Orthanc is down/unreachable, the service is not interrupted.
    Then, there is a need for a nightly check: if a resource is missing from Orthanc-2 it has
    to be copied from Orthanc-1 to Orthanc-2 (and vice-versa).

    ## Challenge
    The `Comparator` tool does the exact same job... but it relies on the StudyDate for the queries.
    While this is great for a medical PACS, this won't work in research context, indeed, the
    stored resources could have a StudyDate in the far past...

    ## Trick
    The Syncher will query to `*` and filter on `LastUpdate` metadata. Then for each result, it
    will query the other Orthanc to check if the resource(s) is(are) also there (and act
    if needed).
    The latest value of the LastUpdate metadata is stored, so that the next check (next night),
    it will process only the recently modified resources.

    ## How it works
    There are 2 runs:
    First run to process the studies from Orthanc-1;
    Second run to process the studies from Orthanc-2.

    Each run will:
    - Get the list of all studies (by batches of 100)
    - For each study:
        - read the `LastUpdate` value
        - if `LastUpdate` < `LastProcessedLastUpdate`:
            - end of run.
        - if the study is not present in the other Orthanc:
            - send the study to the other Orthanc
        - else for each series of the study:
            - if the series is not present in the other Orthanc:
                - send the series to the other Orthanc
            - else for each instance of the series:
                - if the instance is not present in the other Orthanc:
                    - send the instance to the other Orthanc
    '''

    def __init__(self,
                 api_client_1: OrthancApiClient,
                 api_client_2: OrthancApiClient,
                 level: str = 'Series',
                 scheduler: Scheduler = None,
                 error_log_file_path: str = None,
                 persist_status_path: str = None,
                 run_till_last_update_1: datetime.datetime = None,
                 run_till_last_update_2: datetime.datetime = None,
                 execution_time: str = None,
                 execution_day: str = None,
                 orthanc_queries_batch_size: int = 100
                 ):

        if level not in ["Study", "Series", "Instance"]:
            raise RuntimeError("Invalid value for argument 'level'")

        self._api_client_1 = api_client_1
        self._api_client_2 = api_client_2
        self._scheduler = scheduler
        self._level = level
        self._error_log_file_path = error_log_file_path
        self._persist_status_path = persist_status_path

        self._current_run = "unknown"

        # first, we get the `run till` value from the file...
        if self._persist_status_path is not None:
            self._run_till_last_update_1, self._run_till_last_update_2 = self._read_status_from_file()

        # ...then, if there is nothing from the file, we try the arg of the constructor...
        else:
            if run_till_last_update_1 is not None:
                self._run_till_last_update_1 = run_till_last_update_1

            # ...finally, if nothing is in the args, we will process the entire content of Orthanc...
            else:
                self._run_till_last_update_1 = datetime.datetime(year=2025, month=1, day=1, hour=1, minute=1, second=1)

            if run_till_last_update_2 is not None:
                self._run_till_last_update_2 = run_till_last_update_2
            else:
                self._run_till_last_update_2 = datetime.datetime(year=2025, month=1, day=1, hour=1, minute=1, second=1)

        self._execution_time = execution_time
        self._execution_day = execution_day

        self._periodic_mode_enabled = False
        if self._execution_day is not None and self._execution_time is not None:
            self._periodic_mode_enabled = True

        self._batch_size = orthanc_queries_batch_size

    def _read_status_from_file(self):
        """
        The file should contain something like that:

        2025-05-20 14:01:58
        2025-05-19 15:44:36

        """
        try:
            with open(self._persist_status_path) as f:
                last_update_strings = f.read().splitlines()
        except (ValueError, FileNotFoundError):  # if can not read, use 1-1-1950
            logger.warning("Could not read LastUpdate values from file, running till at 01-01-1950")
            first_january_1950 = datetime.datetime(year=1950, month=1, day=1, hour=1, minute=1, second=1)

            with open(self._persist_status_path, 'w') as f:
                full_line = datetime.datetime.strftime(first_january_1950, "%Y-%m-%d %H:%M:%S") + '\n'
                f.writelines([full_line, full_line])
            return first_january_1950, first_january_1950

        last_update_1 = datetime.datetime.strptime(last_update_strings[0], "%Y-%m-%d %H:%M:%S")
        last_update_2 = datetime.datetime.strptime(last_update_strings[1], "%Y-%m-%d %H:%M:%S")

        logger.info(f"Orthanc-1 till value from file = {last_update_1}")
        logger.info(f"Orthanc-2 till value from file = {last_update_2}")
        return last_update_1, last_update_2

    def execute(self):

        # if one of the periodic mode parameters is missing, let's go for the regular mode
        if not self._periodic_mode_enabled:
            logger.info("----- Initializing Orthanc syncher (REGULAR mode, will run once)...")
            self._execute()
        else:
            logger.info("----- Initializing Orthanc syncher (PERIODIC mode, will run on a periodic basis)...")
            # 2 following lines allow to use a string as a method
            schedule_method = getattr(schedule.every(), self._execution_day)
            schedule_method.at(self._execution_time).do(self._execute)
            while True:
                schedule.run_pending()
                time.sleep(1)

    def _execute(self):
        # First run (Orthanc-1 studies are processed and pushed to Orthanc-2 if needed)

        self._current_run = "1 -> 2"
        logger.info(f"Starting run 1 ({self._current_run})...")

        self._run_till_last_update_1 = self.synch(
            orthanc_source=self._api_client_1,
            orthanc_destination=self._api_client_2,
            last_update_limit=self._run_till_last_update_1
        )

        if self._persist_status_path is not None:
            self.save_last_update_limit(self._run_till_last_update_1, 0)

        # Second run (Orthanc-2 studies are processed and pushed to Orthanc-1 if needed)

        self._current_run = "2 -> 1"
        logger.info(f"Starting run 2 ({self._current_run})...")

        self._run_till_last_update_2 = self.synch(
            orthanc_source=self._api_client_2,
            orthanc_destination=self._api_client_1,
            last_update_limit=self._run_till_last_update_2
        )
        if self._persist_status_path is not None:
            self.save_last_update_limit(self._run_till_last_update_2, 1)

    def synch(self, orthanc_source: OrthancApiClient, orthanc_destination: OrthancApiClient, last_update_limit: datetime.datetime) -> datetime.datetime:

        index=0
        while True:
            # Get a batch of studies
            studies = self.get_studies(orthanc_client=orthanc_source, batch_size=self._batch_size, index=index)

            logger.info(f"[{self._current_run}] Processing batch index {index}...")

            if index == 0:
                new_last_update_limit = studies[0].last_update

            for study in studies:
                if study.last_update >= last_update_limit:
                    self.compare_studies(orthanc_source, orthanc_destination, study.orthanc_id)
                else:
                    # the current study LastUpdate value is older than the most recent value checked during the last run, so it's over
                    # let's return the new_last_update_limit

                    logger.info(f"[{self._current_run}] Reached the 'LastUpdate' value already processed during last run, end of this run!")
                    return new_last_update_limit

            if len(studies) < self._batch_size:
                # if the actual batch size is less than the expected, all studies have been processed --> stop
                logger.info(f"[{self._current_run}] Processed all studies, end of this run!")
                return new_last_update_limit

            else:
                # if not, let's fetch the next batch
                index = index + self._batch_size

    def save_last_update_limit(self, new_last_update_value: datetime.datetime, index: int):
        try:
            # read file
            with open(self._persist_status_path, 'r') as f:
                last_update_strings = f.read().splitlines()

            # replace values
            last_update_strings[index] = datetime.datetime.strftime(new_last_update_value, "%Y-%m-%d %H:%M:%S")

            # write file
            with open(self._persist_status_path, 'w') as f:
                f.writelines(line + '\n' for line in last_update_strings)

        except (ValueError, FileNotFoundError):
            logger.error("Could not write LastUpdate values to file!")
            exit(0)

    def compare_studies(self, orthanc_source: OrthancApiClient, orthanc_destination: OrthancApiClient, orthanc_study_id):
        # check if study is in distant Orthanc
        if not orthanc_destination.studies.exists(orthanc_study_id):
            # if not there, transfer it
            instances_ids = orthanc_source.studies.get_instances_ids(orthanc_study_id)
            self.transfer_instances(orthanc_source, orthanc_destination, instances_ids)

        # study is there, let's check series/instances according to level
        elif self._level != "Study":
            source_series = orthanc_source.studies.get_series_ids(orthanc_study_id)
            for series_id in source_series:
                if not orthanc_destination.series.exists(series_id):
                    # this series is not in destination, transfer it
                    instances_ids = orthanc_source.series.get_instances_ids(series_id)
                    self.transfer_instances(orthanc_source, orthanc_destination, instances_ids)
                # series is there, let's check instances according to level
                elif self._level == "Instance":
                    source_instances = orthanc_source.series.get_instances_ids(series_id)
                    for instance_id in source_instances:
                        if not orthanc_destination.instances.exists(instance_id):
                            self.transfer_instances(orthanc_source, orthanc_destination, [instance_id])


    def transfer_instances(self, orthanc_source: OrthancApiClient, orthanc_destination: OrthancApiClient, instances_ids: List[str]):

        retry_count = 0
        retry_delays = [5, 20, 60, 300, 900, 1800, 3600, 7200]

        while retry_count <= 5:
            if retry_count >= 1:
                delay = retry_delays[retry_count - 1]
                logger.info(f"waiting {delay} seconds before retrying transfer for resource from study {orthanc_source.instances.get_parent_study_id(instances_ids[0])}")
                time.sleep(delay)

            try:
                for instance_id in instances_ids:
                    data = orthanc_source.instances.get_file(instance_id)
                    orthanc_destination.upload(data)

                break

            except Exception as e:
                if retry_count == 5:
                    logger.error(f"Error while transfering a resource from this study: {orthanc_source.instances.get_parent_study_id(instances_ids[0])}. Exception: {str(e)}")
                    exit(0)
                else:
                    retry_count += 1
                    logger.warning(f"Error while transfering a resource from this study: {orthanc_source.instances.get_parent_study_id(instances_ids[0])}. Exception: {str(e)}")

    def get_studies(self, orthanc_client: OrthancApiClient, batch_size: int, index: int):
        return orthanc_client.studies.find(
            query={},
            limit = batch_size,
            since = index,
            order_by = [
                {
                    "Type": "Metadata",
                    "Key": "LastUpdate",
                    "Direction": "DESC"
                }
            ]
        )


if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description='Ensure that all the studies/series/instances stored in Orthanc-1 are also stored in Orthanc-2.')
    parser.add_argument('--url_1', type=str, default='http://localhost:8042', help='Orthanc-1 url')
    parser.add_argument('--user_1', type=str, default=None, help='Orthanc-1 user name')
    parser.add_argument('--password_1', type=str, default=None, help='Orthanc-1 password')
    parser.add_argument('--api_key_1', type=str, default=None, help='Orthanc-1 api-key')
    parser.add_argument('--url_2', type=str, default='http://localhost:8042', help='Orthanc-2 url')
    parser.add_argument('--user_2', type=str, default=None, help='Orthanc-2 user name')
    parser.add_argument('--password_2', type=str, default=None, help='Orthanc-2 password')
    parser.add_argument('--api_key_2', type=str, default=None, help='Orthanc-2 api-key')
    parser.add_argument('--level', type=str, default='Series', help='Compare resources up to Study/Series/Instance level')
    parser.add_argument('--error_log_file_path', type=str, default='/errors.log', help='Path to the file to write errors log')
    parser.add_argument('--persist_status_path', type=str, default='/status.txt', help='Path to the file to write the status')

    parser.add_argument('--execution_time', type=str, default=None,
                        help='Enables periodic mode. The time when the periodic run will start (format: 23:30 or 23:30:14).')
    parser.add_argument('--execution_day', type=str, default=None,
                        help='Enables periodic mode. The day when the periodic run will start. All days of the week are valid values (lowercase), \'day\' is also accepted for everyday runs.')

    Scheduler.add_parser_arguments(parser)

    args = parser.parse_args()

    url_1 = os.environ.get("ORTHANC_1_URL", args.url_1)
    user_1 = os.environ.get("ORTHANC_1_USER", args.user_1)
    password_1 = os.environ.get("ORTHANC_1_PWD", args.password_1)
    api_key_1 = os.environ.get("ORTHANC_1_API_KEY", args.api_key_1)
    
    url_2 = os.environ.get("ORTHANC_2_URL", args.url_2)
    user_2 = os.environ.get("ORTHANC_2_USER", args.user_2)
    password_2 = os.environ.get("ORTHANC_2_PWD", args.password_2)
    api_key_2 = os.environ.get("ORTHANC_2_API_KEY", args.api_key_2)
    
    level = os.environ.get("LEVEL", args.level)

    error_log_file_path = os.environ.get("ERROR_LOG_FILE_PATH", args.error_log_file_path)
    persist_status_path = os.environ.get("PERSIST_STATUS_PATH", args.persist_status_path)
    
    execution_time = os.environ.get("EXECUTION_TIME", args.execution_time)
    execution_day = os.environ.get("EXECUTION_DAY", args.execution_day)

    scheduler = Scheduler.create_from_args_and_env_var(args)

    api_client_1 = None
    if api_key_1 is not None:
        api_client_1 = OrthancApiClient(url_1, headers={"api-key" : api_key_1})
    else:
        api_client_1 = OrthancApiClient(url_1, user=user_1, pwd=password_1)
        
    api_client_2 = None
    if api_key_2 is not None:
        api_client_2 = OrthancApiClient(url_2, headers={"api-key" : api_key_2})
    else:
        api_client_2 = OrthancApiClient(url_2, user=user_2, pwd=password_2)



    syncher = OrthancSyncher(
        api_client_1=api_client_1,
        api_client_2=api_client_2,
        level=level,
        scheduler=scheduler,
        error_log_file_path=error_log_file_path,
        persist_status_path=persist_status_path,
        execution_time=execution_time,
        execution_day=execution_day
    )

    syncher.execute()



