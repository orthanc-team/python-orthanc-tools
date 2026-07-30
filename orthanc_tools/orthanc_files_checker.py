'''
# Summary
This script will check that every single instance of an Orthanc has actually a file in the storage location.
It will ouput a csv file with the following information:

PatientID,PatientName,StudyDate,StudyDescription,StudyInstanceUID,MissingFilePath

The script will get the list of all studies.
For each study:
    It will check every instance.
    If an instance is missing, the study is logged and it moves to the next study

'''

import datetime

import schedule
import time
import argparse
import logging
from typing import List
import os
from orthanc_api_client import OrthancApiClient, helpers
import csv

logger = logging.getLogger(__name__)

class OrthancFilesChecker:

    def __init__(self,
                 api_client: OrthancApiClient,
                 missing_files_list_file_path: str
                 ):
        self._api_client = api_client
        self._missing_files_list_file_path = missing_files_list_file_path

    def check(self):

        # get all studies
        all_studies_ids = self._api_client.studies.get_all_ids()

        total_amount_of_studies = len(all_studies_ids)
        logger.info(f"Will proceed {total_amount_of_studies} studies...")

        i=0
        # for each study
        for study_id in all_studies_ids:
            i += 1
            logger.info(f"Processing study {i} out of {total_amount_of_studies}...")

            instances_ids = self._api_client.studies.get_instances_ids(study_id)

            # for each instance
            for instance_id in instances_ids:
                try:
                    self._api_client.instances.get_file(instance_id)
                except:
                    study = self._api_client.studies.get(orthanc_id=study_id)
                    self.add_study_to_list(study)
                    break


    def add_study_to_list(self, study):
        '''
        add a line to the file with the study_info
        '''

        PatientID = study.patient_main_dicom_tags.get("PatientID")
        PatientName = study.patient_main_dicom_tags.get("PatientName")
        StudyDate = study.main_dicom_tags.get("StudyDate")
        StudyDescription = study.main_dicom_tags.get("StudyDescription")
        StudyInstanceUID = study.main_dicom_tags.get("StudyInstanceUID")

        with open(self._missing_files_list_file_path, "a") as f:
            f.write(f'{PatientID},{PatientName},{StudyDate},{StudyDescription},{StudyInstanceUID}\n')


    def execute(self):
        logger.info("----- Initializing Orthanc Checker...")
        self.check()


# example:
# python orthanc_tools/orthanc_files_checker.py --orthanc_url=http://192.168.0.10:8042 --orthanc_user=user --orthanc_pwd=pwd --missing_files_list_file_path=./missing_files.csv

if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(
        description='Check that every single instance of an Orthanc has actually a file in the storage location.')
    parser.add_argument('--orthanc_url', type=str, default=None, help='Orthanc source url')
    parser.add_argument('--orthanc_user', type=str, default=None, help='Orthanc source user name')
    parser.add_argument('--orthanc_pwd', type=str, default=None, help='Orthanc source password')
    parser.add_argument('--orthanc_api_key', type=str, default=None, help='Orthanc api-key')
    parser.add_argument('--missing_files_list_file_path', type=str, default=None,
                        help='Path of the file containing the list of missing files')

    args = parser.parse_args()

    orthanc_url = os.environ.get("ORTHANC_URL", args.orthanc_url)
    orthanc_user = os.environ.get("ORTHANC_USER", args.orthanc_user)
    orthanc_pwd = os.environ.get("ORTHANC_PWD", args.orthanc_pwd)
    orthanc_api_key = os.environ.get("ORTHANC_API_KEY", args.orthanc_api_key)
    missing_files_list_file_path = os.environ.get("MISSING_FILES_LIST_FILE_PATH", args.missing_files_list_file_path)

    api_client = None
    if orthanc_api_key is not None:
        api_client = OrthancApiClient(orthanc_url, headers={"api-key": orthanc_api_key})
    else:
        api_client = OrthancApiClient(orthanc_url, user=orthanc_user, pwd=orthanc_pwd)

    checker = OrthancFilesChecker(
        api_client=api_client,
        missing_files_list_file_path=missing_files_list_file_path
    )

    checker.execute()



