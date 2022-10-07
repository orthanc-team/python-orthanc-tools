import os
import logging
import argparse
import datetime
from .scheduler import Scheduler
from orthanc_api_client import helpers

from orthanc_api_client import OrthancApiClient

class OrthancComparator:

    def __init__(self,
                 api_client: OrthancApiClient,
                 from_study_date: datetime.date,  # Start date
                 to_study_date: datetime.date,  # End date
                 modality: str,  # modality as configured in Orthanc (alias)
                 level: str = 'Series',
                 scheduler: Scheduler = None,
                 transfer_missing_to_modality: bool = False,
                 ignore_missing_from_orthanc: bool = False,
                 retrieve_missing_from_orthanc: bool = False,
                 ignore_missing_on_modality: bool = False,
                 logger: logging.Logger = logging.getLogger('orthanc_tools')
                 ):

        if level not in ["Study", "Series", "Instance"]:
            raise RuntimeError("Invalid value for argument 'level'")

        self._api_client = api_client
        self._modality = modality
        self._from_study_date = from_study_date
        self._to_study_date = to_study_date
        self._scheduler = scheduler
        self._level = level
        self._transfer_missing_to_modality = transfer_missing_to_modality
        self._ignore_missing_from_orthanc = ignore_missing_from_orthanc
        self._retrieve_missing_from_orthanc = retrieve_missing_from_orthanc
        self._ignore_missing_on_modality = ignore_missing_on_modality
        self._logger = logger

    def execute(self):

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
            self.compare_date(current_date)
            current_date += datetime.timedelta(days=inc_date)

    def compare_date(self, current_date: datetime.date):
        if self._scheduler:
            self._scheduler.wait_right_time_to_run(logger=self._logger)

        try:
            self._logger.info("Processing date {date}".format(date=str(current_date)))

            local_studies = self._api_client.studies.find(
                query={
                    'StudyDate': helpers.to_dicom_date(current_date)
                })
            remote_studies = self._api_client.modalities.query_studies(
                from_modality=self._modality,
                query={
                    'StudyDate': helpers.to_dicom_date(current_date),
                    'PatientID': '',
                    'PatientName': '',
                    'StudyInstanceUID': '',
                    'StudyDescription': ''
                })

            self._logger.info(f"{str(current_date)}")
            self._logger.info(f"=======================================")
            if len(local_studies) != len(remote_studies):
                self._logger.warning(f"WARNING {str(current_date)}: {len(local_studies)} studies in Orthanc, {len(remote_studies)} studies in modality")
            else:
                self._logger.info(f"found {len(local_studies)} studies on both side")

            for local_study in local_studies:

                try:
                    remote_match = [r for r in remote_studies if r.dicom_id == local_study.dicom_id]
                    study_summary = f"{local_study.patient_main_dicom_tags.get('PatientID')} - {local_study.patient_main_dicom_tags.get('PatientName')} - {local_study.main_dicom_tags.get('StudyDescription')}"

                    if len(remote_match) == 0 and not self._ignore_missing_on_modality:
                        self._logger.warning(f"WARNING {str(current_date)}, study missing on modality: {study_summary}")
                        if self._transfer_missing_to_modality:
                            self._logger.warning(f"WARNING {str(current_date)}, transferring study to modality: {study_summary}")
                            self._api_client.modalities.store(
                                target_modality=self._modality,
                                resources_ids=local_study.orthanc_id,
                                synchronous=True
                            )
                    elif len(remote_match) > 1:
                        self._logger.warning(f"WARNING {str(current_date)}, study found multiple times on modality: {study_summary}")
                    elif len(remote_match) == 1:
                        if self._level in ['Series', 'Instance']:
                            self.compare_study(orthanc_id=local_study.orthanc_id, dicom_id=local_study.dicom_id, study_summary=study_summary)
                except Exception as ex:
                    self._logger.error(f"ERROR: {str(ex)}")

            if not self._ignore_missing_from_orthanc:
                for remote_study in remote_studies:
                    try:

                        local_match = [l for l in local_studies if l.dicom_id == remote_study.dicom_id]
                        if len(local_match) == 0:
                            self._logger.warning(f"WARNING {str(current_date)}, study missing from Orthanc: {remote_study.tags.get('PatientID')} - {remote_study.tags.get('PatientName')} - {remote_study.tags.get('StudyDescription')}")
                            if self._retrieve_missing_from_orthanc:
                                self._logger.warning(f"WARNING {str(current_date)}, retrieving missing study from Orthanc: {remote_study.tags.get('PatientID')} - {remote_study.tags.get('PatientName')} - {remote_study.tags.get('StudyDescription')}")
                                self._api_client.modalities.move_study(
                                    from_modality=self._modality,
                                    dicom_id=remote_study.dicom_id
                                )
                        elif len(local_match) > 1:
                            self._logger.warning(f"WARNING {str(current_date)}, study found multiple times on Orthanc: {remote_study.tags.get('PatientID')} - {remote_study.tags.get('PatientName')} - {remote_study.tags.get('StudyDescription')}")
                        # elif self._ignore_missing_on_modality: # in this case only, study comparison has not been performed above -> do it now
                    except Exception as ex:
                        self._logger.error(f"ERROR: {str(ex)}")

        except Exception as ex:
            self._logger.error(f"ERROR: {str(ex)}")


    def compare_study(self, orthanc_id: str, dicom_id: str, study_summary: str):
        if self._scheduler:
            self._scheduler.wait_right_time_to_run(self._logger)

        try:

            local_series = self._api_client.get_json(f"/studies/{orthanc_id}/series?expand")

            remote_series = self._api_client.modalities.query_series(
                from_modality=self._modality,
                query={
                    'StudyInstanceUID': dicom_id,
                    'SeriesInstanceUID': '',
                    'SeriesDescription': ''
                })

            if len(local_series) != len(remote_series):
                self._logger.warning(f"WARNING STUDY {study_summary}: {len(local_series)} series in Orthanc, {len(remote_series)} series in modality")

            for local_serie in local_series:
                local_dicom_id = local_serie.get('MainDicomTags').get('SeriesInstanceUID')
                remote_match = [r for r in remote_series if r.dicom_id == local_dicom_id]
                if len(remote_match) == 0 and not self._ignore_missing_on_modality:
                    self._logger.warning(f"WARNING STUDY {study_summary}, series missing from modality: {local_dicom_id}")
                    if self._transfer_missing_to_modality:
                        self._logger.warning(f"WARNING STUDY {study_summary}, transferring series to modality: {local_dicom_id}")
                        self._api_client.modalities.store(
                            target_modality=self._modality,
                            resources_ids=local_serie.get('ID'),
                            synchronous=True
                        )
                elif len(remote_match) > 1:
                    self._logger.warning(f"WARNING STUDY {study_summary}, series found multiple times on modality: {local_dicom_id}")
                elif len(remote_match) == 1:
                    series_summary = f"{local_dicom_id} (from STUDY {study_summary})"
                    if self._level in ['Instance']:
                        self.compare_series(
                            orthanc_id=local_serie.get('ID'),
                            dicom_id=local_dicom_id,
                            study_dicom_id=dicom_id,
                            series_summary=series_summary)

            if not self._ignore_missing_from_orthanc:
                for remote_serie in remote_series:
                    local_match = [l for l in local_series if l.get('MainDicomTags').get('SeriesInstanceUID') == remote_serie.dicom_id]
                    if len(local_match) == 0:
                        self._logger.warning(f"WARNING STUDY {dicom_id}, series missing from Orthanc: {remote_serie.dicom_id}")
                        if self._retrieve_missing_from_orthanc:
                            self._logger.warning(f"WARNING STUDY {dicom_id}, retrieving missing series from Orthanc: {remote_serie.dicom_id}")
                            self._api_client.modalities.move_series(
                                from_modality=self._modality,
                                dicom_id=remote_serie.dicom_id,
                                study_dicom_id=dicom_id
                            )
                    elif len(local_match) > 1:
                        self._logger.warning(f"WARNING STUDY {dicom_id}, series found multiple times on Orthanc: {remote_serie.dicom_id}")
        except Exception as ex:
            self._logger.exception(f"ERROR: {str(ex)}")


    def compare_series(self, orthanc_id: str, dicom_id: str, study_dicom_id: str, series_summary: str):

        try:
            local_instances = self._api_client.get_json(f"/series/{orthanc_id}/instances?expand")

            remote_instances = self._api_client.modalities.query_instances(
                from_modality=self._modality,
                query={
                    'SeriesInstanceUID': dicom_id,
                    'SOPInstanceUID': ''
                })

            if len(local_instances) != len(remote_instances):
                self._logger.warning(f"WARNING SERIES {series_summary}: {len(local_instances)} instances in Orthanc, {len(remote_instances)} instances in modality")

            success_count = 0
            failure_count = 0

            for local_instance in local_instances:
                try:
                    local_dicom_id = local_instance.get('MainDicomTags').get('SOPInstanceUID')
                    remote_match = [r for r in remote_instances if r.dicom_id == local_dicom_id]

                    if len(remote_match) == 0 and not self._ignore_missing_on_modality:
                        self._logger.warning(f"WARNING SERIES {series_summary}, instance missing from modality: {local_dicom_id}")
                        if self._transfer_missing_to_modality:
                            self._logger.warning(f"WARNING SERIES {series_summary}, transferring instance to modality: {local_dicom_id}")
                            self._api_client.modalities.store(
                                target_modality=self._modality,
                                resources_ids=local_instance.get('ID'),
                                synchronous=True
                            )
                            success_count += 1
                    elif len(remote_match) > 1:
                        self._logger.warning(f"WARNING SERIES {series_summary}, instance found multiple times on modality: {local_dicom_id}")
                except:
                    failure_count += 1

            if not self._ignore_missing_from_orthanc:
                for remote_instance in remote_instances:
                    try:
                        local_match = [l for l in local_instances if l.get('MainDicomTags').get('SOPInstanceUID') == remote_instance.dicom_id]
                        if len(local_match) == 0:
                            self._logger.warning(f"WARNING SERIES {series_summary}, instance missing from Orthanc: {remote_instance.dicom_id}")
                            if self._retrieve_missing_from_orthanc:
                                self._logger.warning(f"WARNING SERIES {series_summary}, retrieving instance missing from Orthanc: {remote_instance.dicom_id}")
                                self._api_client.modalities.move_instance(
                                    from_modality=self._modality,
                                    dicom_id=remote_instance.dicom_id,
                                    series_dicom_id=dicom_id,
                                    study_dicom_id=study_dicom_id
                                )
                                success_count += 1
                        elif len(local_match) > 1:
                            self._logger.warning(f"WARNING SERIES {series_summary}, instance found multiple times on Orthanc: {remote_instance.dicom_id}")
                    except Exception as ex:
                        failure_count += 1

            if failure_count > 0:
                self._logger.error(f"ERROR SERIES {series_summary}, transferring/retrieving instances: {failure_count} failure, {success_count} success")
            elif success_count > 0:
                self._logger.warning(f"WARNING SERIES {series_summary}, transferred: {success_count} instances")

        except Exception as ex:
            self._logger.error(f"ERROR: {str(ex)}")


if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description='Compare the content of Orthanc with the content of a remote modality')
    parser.add_argument('--url', type=str, default='http://localhost:8042', help='Orthanc url')
    parser.add_argument('--user', type=str, default=None, help='Orthanc user name')
    parser.add_argument('--password', type=str, default=None, help='Orthanc password')
    parser.add_argument('--modality', type=str, required=True, help='Alias of the modality to compare with (in Orthanc config)')
    parser.add_argument('--from_study_date', type=str, required=True, help='From Study Date (format 20190225)')
    parser.add_argument('--to_study_date', type=str, required=True, help='To Study Date (format 20190225)')
    parser.add_argument('--level', type=str, default='Series', help='Compare resources up to Study/Series/Instance level')
    parser.add_argument('--transfer_missing_to_modality', default=False, action='store_true', help='Transfer missing resources from Orthanc to the remote modality')
    parser.add_argument('--ignore_missing_from_orthanc', default=False, action='store_true', help="Don't generate a warning if resources are missing from Orthanc")
    parser.add_argument('--retrieve_missing_from_orthanc', default=False, action='store_true', help='Retrieve missing resources to Orthanc from the remote modality')
    parser.add_argument('--ignore_missing_on_modality', default=False, action='store_true', help="Don't generate a warning if resources are missing on the remote modality")
    # TODO parser.add_argument('--retrieve_missing_in_orthanc', default=False, action='store_true', help='Retrieve missing resources from remote modality into Orthanc')
    Scheduler.add_parser_arguments(parser)

    args = parser.parse_args()

    url = os.environ.get("ORTHANC_URL", args.url)
    user = os.environ.get("ORTHANC_USER", args.user)
    password = os.environ.get("ORTHANC_PWD", args.password)
    modality = os.environ.get("MODALITY", args.modality)
    level = os.environ.get("LEVEL", args.level)
    from_study_date = helpers.from_dicom_date(os.environ.get("FROM_STUDY_DATE", args.from_study_date))
    to_study_date = helpers.from_dicom_date(os.environ.get("TO_STUDY_DATE", args.to_study_date))
    transfer_missing_to_modality = os.environ.get("TRANSFER_MISSING_TO_MODALITY", args.transfer_missing_to_modality)
    ignore_missing_from_orthanc = os.environ.get("IGNORE_MISSING_FROM_ORTHANC", args.ignore_missing_from_orthanc)
    retrieve_missing_from_orthanc = os.environ.get("RETRIEVE_MISSING_FROM_ORTHANC", args.retrieve_missing_from_orthanc)
    ignore_missing_on_modality = os.environ.get("IGNORE_MISSING_ON_MODALITY", args.ignore_missing_on_modality)

    scheduler = Scheduler.create_from_args_and_env_var(args)

    comparator = OrthancComparator(
        api_client=OrthancApiClient(url, user=user, pwd=password),
        modality=modality,
        from_study_date=from_study_date,
        to_study_date=to_study_date,
        level=level,
        scheduler=scheduler,
        transfer_missing_to_modality=transfer_missing_to_modality,
        ignore_missing_from_orthanc=ignore_missing_from_orthanc,
        retrieve_missing_from_orthanc=retrieve_missing_from_orthanc,
        ignore_missing_on_modality=ignore_missing_on_modality
    )

    comparator.execute()



