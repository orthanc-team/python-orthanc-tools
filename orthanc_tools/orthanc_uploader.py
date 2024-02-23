import inquirer
from pathlib import Path
import logging
import argparse
from orthanc_api_client import OrthancApiClient

logger = logging.getLogger(__name__)

'''
This script is interactive!
So, run it from the console, follow instructions and enjoy...
'''

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

    def execute(self):

        # let the user choose the folder to upload
        path = self.get_folder(Path(self._path))

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
        print(f"Folder to import: {path}")
        print(f"Labels to apply: {orthanc_labels_chosen_list}")
        questions_continue = [
            inquirer.Confirm("continue", message="Ready to start?", default=True)
        ]

        answers = inquirer.prompt(questions_continue)
        if answers['continue'] == False:
            print("Aborted!")
            exit(-1)

        logger.info(f"starting import of folder {path} ...")
        dicom_ids_set, orthanc_ids_set, rejected_files_list = orthanc_client.upload_folder_return_details(path)

        logger.info(f"starting labeling...")
        for id in orthanc_ids_set:
            orthanc_client.studies.add_labels(orthanc_id=id, labels=orthanc_labels_chosen_list)

        if len(rejected_files_list)>0:
            logger.info("End of upload, here are files in error:")
            for rejected_file in rejected_files_list:
                logger.info(f"{rejected_file[0]} --- {rejected_file[1]}")
        logger.info("End of upload, no errors :-)")


if __name__ == '__main__':
    level = logging.INFO

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="Upload studies from a selected folder and recursively in all subfolders to an Orthanc and apply labels.")
    parser.add_argument('--url', help="The url of the Orthanc to upload studies to.", default="http://localhost:8042")
    parser.add_argument('--user', help="The user of the Orthanc to upload studies to.", default="demo")
    parser.add_argument('--password', help="The password of the Orthanc to upload studies to.", default="demo")
    parser.add_argument('--start_path', help="The path used as start path for the selection of the folder containing studies to upload. Default value: script execution path", default=".")

    args = parser.parse_args()

    orthanc_url = args.url
    orthanc_user = args.user
    orthanc_password = args.password
    start_path = args.start_path

    orthanc_client = OrthancApiClient(orthanc_url, user=orthanc_user, pwd=orthanc_password)

    uploader = OrthancUploader(api_client=orthanc_client, path=start_path)

    uploader.execute()
