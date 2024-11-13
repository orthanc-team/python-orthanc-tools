import inquirer
from pathlib import Path
import logging
import argparse
from orthanc_api_client import OrthancApiClient
import os, time, sys
import zipfile
import tempfile

logger = logging.getLogger(__name__)

'''
This script is interactive!
So, run it from the console, follow instructions and enjoy...
'''

#TODO: modify to use the folder importer!

class OrthancUploader:
    def __init__(self,
                 api_client: OrthancApiClient,
                 path: str
                 ):
        self._api_client = api_client
        self._path = path

    def get_folder(self, current_path = Path('.')):
        """ Print a numbered list of the subfolders in the working directory
        (i.e. the directory the script is run from), and returns the directory
        the user chooses.
        """
        answers = {'studies_path': 'None'}

        while answers['studies_path'] != '.':
            print("Browse to the folder you want to upload to Orthanc, then select the . to validate.")
            questions = [
                inquirer.List(
                    "studies_path",
                    message="Curent folder: " + str(current_path.absolute()),
                    choices=['.'] + ['..'] + [str(d) for d in current_path.iterdir() if d.is_dir()]
                )
            ]
            answers = inquirer.prompt(questions)
            if answers['studies_path'] == '..':
                current_path = current_path.absolute().parent
            elif answers['studies_path'] != '.':
                current_path = Path(answers['studies_path'])
        return str(current_path.absolute())

    def upload_folder_and_label(self, folder_path, labels_list):
        """
        Recursively get the files of the folder to
        - upload each file
        - apply the labels on the study
        """

        for path in os.listdir(folder_path):
            full_path = os.path.join(folder_path, path)
            if os.path.isfile(full_path):

                if zipfile.is_zipfile(full_path):
                    with tempfile.TemporaryDirectory() as tempDir:
                        with zipfile.ZipFile(full_path, 'r') as z:
                            z.extractall(tempDir)
                        self.upload_folder_and_label(folder_path=tempDir, labels_list=labels_list)
                else:
                    retry_count = 0
                    retry_delays = [5, 20, 60, 300, 900, 1800, 3600, 7200]
                    while retry_count <= 8:
                        if retry_count >= 1:
                            delay = retry_delays[retry_count - 1]
                            logger.info(f"waiting {delay} seconds before retrying the upload of {full_path}")
                            time.sleep(delay)
                        try:
                            # here, we should have only files (and no zip file)
                            instance_orthanc_ids = orthanc_client.upload_file(full_path, ignore_errors=True)
                            if len(instance_orthanc_ids) == 0:
                                logger.error(f"File not uploaded: {full_path}.")
                                break
                            study_orthanc_id = orthanc_client.instances.get_parent_study_id(instance_orthanc_ids[0])
                            orthanc_client.studies.add_labels(orthanc_id=study_orthanc_id, labels=labels_list)
                            break
                        except Exception as e:
                            retry_count += 1
                            if retry_count == 8:
                                logger.error(f"Error while uploading this file: {full_path}. Exception: {str(e)}")
                                logger.error(f"too many attempts, exiting...")
                                sys.exit(1)
                            else:
                                logger.warning(f"Error while uploading this file, retrying...: {full_path}. Exception: {str(e)}")
            elif os.path.isdir(full_path):
                self.upload_folder_and_label(folder_path=full_path, labels_list=labels_list)

    def execute(self):

        # let the user choose the folder to upload
        folder_path = self.get_folder(Path(self._path))

        # let's get the existing labels
        labels_list = orthanc_client.get_all_labels()
        orthanc_labels_chosen_list = []

        # let the user choose the labels to apply among the existing ones
        if len(labels_list)>0:
            questions_labels = [
                inquirer.Checkbox(
                    "orthanc_labels_chosen_list",
                    message="Choose the existing labels to apply",
                    choices=labels_list,
                )
            ]

            answers = inquirer.prompt(questions_labels)
            orthanc_labels_chosen_list = answers['orthanc_labels_chosen_list']

        # let the user manually add extra labels
        answers = {'orthanc_extra_label': 'None'}
        while answers['orthanc_extra_label'] != '':
            print(f"Current labels list: {orthanc_labels_chosen_list}")
            questions_labels_manual = [
                inquirer.Text(
                    "orthanc_extra_label",
                    message="Type an extra label to apply, leave it empty and press ENTER if any"
                ),
            ]

            answers = inquirer.prompt(questions_labels_manual)
            orthanc_extra_label = answers['orthanc_extra_label']
            if orthanc_extra_label != "":
                orthanc_labels_chosen_list.append(orthanc_extra_label)

        print("-----------------------------------------------------------------------------------")
        print(f"Folder to import: {folder_path}")
        print(f"Labels to apply: {orthanc_labels_chosen_list}")
        questions_continue = [
            inquirer.Confirm("continue", message="Ready to start?", default=True)
        ]

        answers = inquirer.prompt(questions_continue)
        if answers['continue'] == False:
            print("Aborted!")
            exit(-1)

        logger.info(f"starting import of folder {folder_path} ...")

        self.upload_folder_and_label(folder_path=folder_path, labels_list=orthanc_labels_chosen_list)

        logger.info("End of upload!")


if __name__ == '__main__':
    level = logging.INFO

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="Upload studies from a selected folder and recursively in all subfolders to an Orthanc and apply labels.")
    parser.add_argument('--url', help="The url of the Orthanc to upload studies to.", default="http://localhost:8042")
    parser.add_argument('--user', help="The user of the Orthanc to upload studies to.", default="demo")
    parser.add_argument('--password', help="The password of the Orthanc to upload studies to.", default="demo")
    parser.add_argument('--api_key', type=str, default=None, help='Orthanc api-key')
    parser.add_argument('--start_path', help="The path used as start path for the selection of the folder containing studies to upload. Default value: script execution path", default=".")

    args = parser.parse_args()

    orthanc_url = args.url
    orthanc_user = args.user
    orthanc_password = args.password
    orthanc_api_key = args.api_key
    start_path = args.start_path

    orthanc_client = None
    if orthanc_api_key is not None:
        orthanc_client=OrthancApiClient(orthanc_url, headers={"api-key":orthanc_api_key})
    else:
        orthanc_client=OrthancApiClient(orthanc_url, user=orthanc_user, pwd=orthanc_password)

    uploader = OrthancUploader(api_client=orthanc_client, path=start_path)

    uploader.execute()
