import argparse
import logging
from orthanc_api_client import OrthancApiClient
from typing import List
import zipfile
import tempfile
import os, time, sys

# examples:
# python orthanc_tools/orthanc_folder_importer.py --folder=./tests/stimuli --url=http://192.168.0.10:8042 --user=user --password=pwd --skip=.txt,.ini


logger = logging.getLogger(__name__)

class OrthancFolderImporter:
    '''
    Upload all the DICOM files contained in a folder (and its sub folders).
    It is a little bit smart:
    - There is a retry for every file and when it fails anyway, the file path is logged, but the script keeps working
    - Every sub folder uploaded (even with errors for some files) is logged, so that if the script is interrupted and
    restarted, it will restart from the last succeeded folder.
    - Zip files are unziped before upload
    '''
    def __init__(self,
                 api_client: OrthancApiClient,
                 folder_path: str,
                 errors_path: str,
                 state_path: str,
                 labels_list: List[str] = None,
                 max_retries: int = 8
                 ):
        self._api_client = api_client
        self._folder_path = folder_path
        self._labels_list = labels_list
        self._errors_path = errors_path # will contain the list of all the files path not correctly uploaded
        self._state_path = state_path # will contain the list of all the folders correctly uploaded

        self._folders_uploaded = []

        if max_retries > 8:
            self._max_retries = 8
        else:
            self._max_retries = max_retries

    def add_file_name_in_errors_log(self, file_path):
        with open(self._errors_path, "at") as f:
            f.write(file_path + "\n")

    def add_folder_path_in_state_file(self, folder_path):
        with open(self._state_path, "at") as f:
            f.write(folder_path + "\n")

    def upload_folder_and_label(self, folder_path):
        """
        Recursively get the files of the folder to
        - upload each file
        - apply the labels on the study
        """

        for path in os.listdir(folder_path):
            full_path = os.path.join(folder_path, path)
            if os.path.isfile(full_path):

                if "zip" in full_path and zipfile.is_zipfile(full_path):
                    with tempfile.TemporaryDirectory() as tempDir:
                        with zipfile.ZipFile(full_path, 'r') as z:
                            z.extractall(tempDir)
                        self.upload_folder_and_label(folder_path=tempDir)
                else:
                    retry_count = 0
                    retry_delays = [5, 20, 60, 300, 900, 1800, 3600, 7200]

                    while retry_count <= self._max_retries:
                        if retry_count >= 1:
                            delay = retry_delays[retry_count - 1]
                            logger.info(f"waiting {delay} seconds before retrying the upload of {full_path}")
                            time.sleep(delay)
                        try:
                            # here, we should have only files (and no zip file)
                            instance_orthanc_ids = self._api_client.upload_file(full_path, ignore_errors=True)
                            if len(instance_orthanc_ids) == 0:
                                logger.error(f"File not uploaded: {full_path}.")
                                self.add_file_name_in_errors_log(file_path=full_path)
                                break
                            # we label for each instance, not at the end of the study, so that there is never an unlabeled image in Orthanc
                            if self._labels_list is not None:
                                study_orthanc_id = self._api_client.instances.get_parent_study_id(instance_orthanc_ids[0])
                                self._api_client.studies.add_labels(orthanc_id=study_orthanc_id, labels=self._labels_list)
                            break
                        except Exception as e:
                            if retry_count == self._max_retries:
                                logger.error(f"Error while uploading this file: {full_path}. Exception: {str(e)}")
                                logger.error(f"too many attempts, logging the file name...")
                                self.add_file_name_in_errors_log(file_path=full_path)
                                break
                            else:
                                retry_count += 1
                                logger.warning(f"Error while uploading this file, retrying...: {full_path}. Exception: {str(e)}")
            elif os.path.isdir(full_path):
                # this folder could have been processed in a previous run of the script
                if full_path in self._folders_uploaded:
                    logger.info(f"Folder {full_path} already processed, skipping...")
                    continue

                # let's process this folder
                self.upload_folder_and_label(folder_path=full_path)

                # let's add this folder path in the processed ones:
                self.add_folder_path_in_state_file(full_path)

    def execute(self):
        # read state
        if os.path.isfile(self._state_path):
            with open(self._state_path, 'r') as file:
                lines = file.readlines()
                self._folders_uploaded = [line.strip() for line in lines]

        self.upload_folder_and_label(folder_path=self._folder_path)

        logger.info("End of upload!")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Import the content of a folder in Orthanc')
    parser.add_argument('--url', type=str, default='http://localhost:8042', help='Orthanc url')
    parser.add_argument('--user', type=str, default=None, help='Orthanc user name')
    parser.add_argument('--password', type=str, default=None, help='Orthanc password')
    parser.add_argument('--api_key', type=str, default=None, help='Orthanc api-key')
    parser.add_argument('--folder_path', type=str, help='Folder to import, the one containing the DICOM files.')
    parser.add_argument('--labels_list', type=str, default=None, help='List of labels to apply to the uploaded studies, separated by a comma.')
    parser.add_argument('--errors_path', type=str, help='Path of the file which will contain the list of problematic files (not uploaded).')
    parser.add_argument('--state_path', type=str, help='Path of the file which will contain the list of all the folder correctly uploaded.')
    parser.add_argument('--max_retries', type=int, default=8, help='Maximum number of attempts for a file upload.')

    args = parser.parse_args()

    o = None
    if args.api_key is not None:
        o=OrthancApiClient(args.url, headers={"api-key":args.api_key})
    else:
        o=OrthancApiClient(args.url, user=args.user, pwd=args.password)

    importer = OrthancFolderImporter(
        api_client=o,
        folder_path=args.folder_path,
        labels_list=args.labels_list,
        errors_path=args.errors_path,
        state_path=args.state_path,
        max_retries=args.max_retries
    )

    importer.execute()
