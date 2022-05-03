import os
import logging
import argparse
import datetime
from scheduler import Scheduler
from orthanc_api_client import helpers

from orthanc_api_client import OrthancApiClient
logger = logging.getLogger('orthanc_tools')


class OrthancComparator:

    def __init__(self,
                 api_client: OrthancApiClient,
                 from_study_date: datetime.date,  # Start date
                 to_study_date: datetime.date,  # End date
                 modality: str,  # modality as configured in Orthanc (alias)
                 level: str = 'Series',
                 scheduler: Scheduler = None
                 ):

        if level not in ["Study", "Series", "Instance"]:
            raise RuntimeError("Invalid value for argument 'level'")

        self._api_client = api_client
        self._modality = modality
        self._from_study_date = from_study_date
        self._to_study_date = to_study_date
        self._scheduler = scheduler
        self._level = level

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
            self._scheduler.wait_right_time_to_run(logger=logger)

        logger.info("Processing date {date}".format(date=str(current_date)))

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

        print(f"{str(current_date)}")
        print(f"=======================================")
        if len(local_studies) != len(remote_studies):
            print(f"WARNING {str(current_date)}: {len(local_studies)} studies in Orthanc, {len(remote_studies)} studies in modality")
        else:
            print(f"found {len(local_studies)} studies on both side")

        for local_study in local_studies:
            remote_match = [r for r in remote_studies if r.dicom_id == local_study.dicom_id]
            study_summary = f"{local_study.patient_main_dicom_tags.get('PatientID')} - {local_study.patient_main_dicom_tags.get('PatientName')} - {local_study.main_dicom_tags.get('StudyDescription')}"
            if len(remote_match) == 0:
                print(f"WARNING {str(current_date)}, study missing from modality: {study_summary}")
            elif len(remote_match) > 1:
                print(f"WARNING {str(current_date)}, study found multiple times on modality: {study_summary}")
            else:
                if self._level in ['Series']:
                    self.compare_study(orthanc_id=local_study.orthanc_id, dicom_id=local_study.dicom_id, study_summary=study_summary)

        for remote_study in remote_studies:
            local_match = [l for l in local_studies if l.dicom_id == remote_study.dicom_id]
            if len(local_match) == 0:
                print(f"WARNING {str(current_date)}, study missing from Orthanc: {remote_study.tags.get('PatientID')} - {remote_study.tags.get('PatientName')} - {remote_study.tags.get('StudyDescription')}")
            elif len(local_match) > 1:
                print(f"WARNING {str(current_date)}, study found multiple times on Orthanc: {remote_study.tags.get('PatientID')} - {remote_study.tags.get('PatientName')} - {remote_study.tags.get('StudyDescription')}")

    def compare_study(self, orthanc_id: str, dicom_id: str, study_summary: str):
        if self._scheduler:
            self._scheduler.wait_right_time_to_run(logger)

        local_series = self._api_client.get_json(f"/studies/{orthanc_id}/series?expand")

        remote_series = self._api_client.modalities.query_series(
            from_modality=self._modality,
            query={
                'StudyInstanceUID': dicom_id,
                'SeriesInstanceUID': '',
                'SeriesDescription': ''
            })

        if len(local_series) != len(remote_series):
            print(f"WARNING STUDY {study_summary}: {len(local_series)} series in Orthanc, {len(remote_series)} series in modality")

        for local_serie in local_series:
            local_dicom_id = local_serie.get('MainDicomTags').get('SeriesInstanceUID')
            remote_match = [r for r in remote_series if r.dicom_id == local_dicom_id]
            if len(remote_match) == 0:
                print(f"WARNING STUDY {study_summary}, series missing from modality: {local_dicom_id}")
            elif len(remote_match) > 1:
                print(f"WARNING STUDY {study_summary}, series found multiple times on modality: {local_dicom_id}")
            else:
                series_summary = f"{local_dicom_id} (from STUDY {study_summary})"
                if self._level in ['Instance']:
                    self.compare_series(orthanc_id=local_serie.get('ID'), dicom_id=local_dicom_id, series_summary=series_summary)

        for remote_serie in remote_series:
            local_match = [l for l in local_series if l.get('MainDicomTags').get('SeriesInstanceUID') == remote_serie.dicom_id]
            if len(local_match) == 0:
                print(f"WARNING STUDY {dicom_id}, series missing from Orthanc: {remote_serie.dicom_id}")
            elif len(local_match) > 1:
                print(f"WARNING STUDY {dicom_id}, series found multiple times on Orthanc: {remote_serie.dicom_id}")


    def compare_series(self, orthanc_id: str, dicom_id: str, series_summary: str):

        local_instances = self._api_client.get_json(f"/series/{orthanc_id}/instances?expand")

        remote_instances = self._api_client.modalities.query_instances(
            from_modality=self._modality,
            query={
                'SeriesInstanceUID': dicom_id,
                'SOPInstanceUID': ''
            })

        if len(local_instances) != len(remote_instances):
            print(f"WARNING SERIES {series_summary}: {len(local_instances)} instances in Orthanc, {len(remote_instances)} instances in modality")

        for local_instance in local_instances:
            local_dicom_id = local_instance.get('MainDicomTags').get('SOPInstanceUID')
            remote_match = [r for r in remote_instances if r.dicom_id == local_dicom_id]
            if len(remote_match) == 0:
                print(f"WARNING SERIES {series_summary}, instance missing from modality: {local_dicom_id}")
            elif len(remote_match) > 1:
                print(f"WARNING SERIES {series_summary}, instance found multiple times on modality: {local_dicom_id}")

        for remote_instance in remote_instances:
            local_match = [l for l in local_instances if l.get('MainDicomTags').get('SOPInstanceUID') == remote_instance.dicom_id]
            if len(local_match) == 0:
                print(f"WARNING SERIES {series_summary}, instance missing from Orthanc: {remote_instance.dicom_id}")
            elif len(local_match) > 1:
                print(f"WARNING SERIES {series_summary}, instance found multiple times on Orthanc: {remote_instance.dicom_id}")






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

    # TODO parser.add_argument('--transfer_missing_to_modality', default=False, action='store_true', help='Transfer missing resources from Orthanc to the remote modality')
    # TODO parser.add_argument('--retrieve_missing_in_orthanc', default=False, action='store_true', help='Retrieve missing resources from remote modality into Orthanc')
    Scheduler.add_parser_arguments(parser)

    args = parser.parse_args()

    url = os.environ.get("URL", args.url)
    user = os.environ.get("USER", args.user)
    password = os.environ.get("PASSWORD", args.password)
    modality = os.environ.get("MODALITY", args.modality)
    level = os.environ.get("LEVEL", args.level)
    from_study_date = helpers.from_dicom_date(os.environ.get("FROM_STUDY_DATE", args.from_study_date))
    to_study_date = helpers.from_dicom_date(os.environ.get("TO_STUDY_DATE", args.to_study_date))

    scheduler = Scheduler.create_from_args_and_env_var(args)

    comparator = OrthancComparator(
        api_client=OrthancApiClient(url, user=user, pwd=password),
        modality=modality,
        from_study_date=from_study_date,
        to_study_date=to_study_date,
        level=level,
        scheduler=scheduler
    )

    comparator.execute()



