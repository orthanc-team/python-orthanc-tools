import argparse
import logging
from orthanc_api_client import OrthancApiClient
from typing import List
import zipfile
import tempfile
import os, time, sys
import multiprocessing
import queue
import threading

# examples:
# python orthanc_tools/orthanc_folder_importer.py --folder=./tests/stimuli --url=http://192.168.0.10:8042 --user=user --password=pwd --skip=.txt,.ini

# on a Windows system:
# python -m orthanc_tools.orthanc_folder_importer --url=https://pacs.orthanc.team/orthanc/ --api_key=**************** --folder_path=C:\\Orthanc --state_path=C:\\orthanc-migration\\status.txt --errors_path=C:\\orthanc-migration\\errors.txt --max_retries=2

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
                 max_retries: int = 8,
                 worker_threads_count: int = multiprocessing.cpu_count() - 1  # by default, use all CPUs but one for compression
                 ):
        self._api_client = api_client
        self._folder_path = folder_path
        self._labels_list = labels_list
        self._errors_path = errors_path # will contain the list of all the files path not correctly uploaded
        self._state_path = state_path # will contain the list of all the folders correctly uploaded

        self._worker_threads_count = worker_threads_count
        self._worker_threads = []
        self._messages = queue.Queue(maxsize=2*worker_threads_count)  # this is thread safe https://docs.python.org/3.5/library/queue.html#module-queue

        self._folders_uploaded = []

        if max_retries > 8:
            self._max_retries = 8
        else:
            self._max_retries = max_retries

        self._lock = threading.Lock()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def add_file_name_in_errors_log(self, file_path):
        with open(self._errors_path, "at") as f:
            f.write(file_path + "\n")

    def add_folder_path_in_state_file(self, folder_path):
        if self._state_path:
            with self._lock:
                with open(self._state_path, "at") as f:
                    f.write(folder_path + "\n")

    def upload_and_label(self, path_to_upload):
        """
        Upload the file if path_to_upload is a file path
        Recursively upload the content of the folder is path_to_upload is a folder path
        Then apply the labels on the study
        """

        # file path case
        if os.path.isfile(path_to_upload):

            # zip file case
            if "zip" in path_to_upload and zipfile.is_zipfile(path_to_upload):
                with tempfile.TemporaryDirectory() as tempDir:
                    with zipfile.ZipFile(path_to_upload, 'r') as z:
                        z.extractall(tempDir)
                    for path in os.listdir(tempDir):
                        full_path = os.path.join(tempDir, path)
                        self.upload_and_label(path_to_upload=full_path)
            else:
                retry_count = 0
                retry_delays = [5, 20, 60, 300, 900, 1800, 3600, 7200]

                while retry_count <= self._max_retries:
                    if retry_count >= 1:
                        delay = retry_delays[retry_count - 1]
                        logger.info(f"waiting {delay} seconds before retrying the upload of {path_to_upload}")
                        time.sleep(delay)
                    try:
                        # here, we should have only files (and no zip file)

                        # let's modify/filter the file if needed
                        with open(path_to_upload, 'rb') as f:
                            buffer = f.read()
                            buffer = self.process_dicom_file(buffer)

                        # filtering out case
                        if buffer is None:
                            logger.debug(f"File {path_to_upload} has been filtered out.")
                            return

                        # modification case: let's upload the file
                        logger.info(f"uploading {path_to_upload}")
                        instance_orthanc_ids = self._api_client.upload(buffer, ignore_errors=True)

                        if len(instance_orthanc_ids) == 0:
                            logger.error(f"File not uploaded: {path_to_upload}.")
                            self.add_file_name_in_errors_log(file_path=path_to_upload)
                            break
                        # we label for each instance, not at the end of the study, so that there is never an unlabeled image in Orthanc
                        if self._labels_list is not None:
                            study_orthanc_id = self._api_client.instances.get_parent_study_id(instance_orthanc_ids[0])
                            self._api_client.studies.add_labels(orthanc_id=study_orthanc_id, labels=self._labels_list)
                        break
                    except Exception as e:
                        if retry_count == self._max_retries:
                            logger.error(f"Error while uploading this file: {path_to_upload}. Exception: {str(e)}")
                            logger.error(f"too many attempts, logging the file name...")
                            self.add_file_name_in_errors_log(file_path=path_to_upload)
                            break
                        else:
                            retry_count += 1
                            logger.warning(f"Error while uploading this file, retrying...: {path_to_upload}. Exception: {str(e)}")
        # folder case
        elif os.path.isdir(path_to_upload):
            # this folder could have been processed in a previous run of the script
            if path_to_upload in self._folders_uploaded:
                logger.info(f"Folder {path_to_upload} already processed, skipping...")
                return

            # let's process this folder
            for path in os.listdir(path_to_upload):
                full_path = os.path.join(path_to_upload, path)
                self.upload_and_label(path_to_upload=full_path)

            # let's add this folder path in the processed ones:
            self.add_folder_path_in_state_file(path_to_upload)

    def process_dicom_file(self, file_content: bytes) -> bytes:
        '''
        This method is called just before the upload of the file to Orthanc
        By default, nothing is done, but one could want to apply some modifications on the data before upload
        or to filter out some files.
        To do so, this method should be overridden in a derived class.
        If the goal is to filter out the file, 'None' should be returned.

        file_content: content of the DICOM file, as a buffer of bytes
        output: a buffer of bytes (None to filter out the file)
        '''
        return file_content

    def _process_path(self, worker_id):
        logger.debug(f"Starting Processing thread {worker_id}")

        while True:
            path = self._messages.get()  # block until a message is available

            if path is None:  # sent by stop() to stop all worker threads
                self._messages.task_done()
                break

            # path is the full path of a file or a folder
            self.upload_and_label(path_to_upload=path)

            self._messages.task_done()  # tell the queue the item has been processed

        logger.debug("Processing thread stopped")

    def execute(self):
        # read state
        if self._state_path and os.path.isfile(self._state_path):
            with open(self._state_path, 'r') as file:
                lines = file.readlines()
                self._folders_uploaded = [line.strip() for line in lines]

        # create worker threads
        for thread_id in range(0, self._worker_threads_count):
            self._worker_threads.append(threading.Thread(
                target=self._process_path,
                name=f"Worker Thread {thread_id}",
                args=(thread_id, )
            ))

        # start threads
        for wt in self._worker_threads:
            wt.start()

        # let's browse the main folder to feed the message queue
        for path in os.listdir(path=self._folder_path):
            full_path = os.path.join(self._folder_path, path)
            self._messages.put(full_path) # if the queue is full, this will block until there's a free slot

        # let's wait for the completion of all threads
        self.stop()

        logger.info("End of upload!")

    def stop(self):
        logger.info("Waiting for Orthanc Folder Importer to complete each upload...")

        # post one 'empty' exit message per thread to unlock the threads from waiting on the process queue
        for i in range(0, self._worker_threads_count):
            self._messages.put(None)

        for t in self._worker_threads:
            t.join()

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
    parser.add_argument('--worker_threads_count', type=int, default=1, help='Worker threads count')

    args = parser.parse_args()

    url = os.environ.get("ORTHANC_URL", args.url)
    user = os.environ.get("ORTHANC_USER", args.user)
    password = os.environ.get("ORTHANC_PWD", args.password)
    api_key = os.environ.get("ORTHANC_API_KEY", args.api_key)
    folder_path = os.environ.get("FOLDER_PATH", args.folder_path)
    labels_list = os.environ.get("LABELS_LIST", args.labels_list)
    errors_path = os.environ.get("ERRORS_PATH", args.errors_path)
    state_path = os.environ.get("STATE_PATH", args.state_path)
    max_retries = int(os.environ.get("MAX_RETRIES", str(args.max_retries)))
    worker_threads_count = int(os.environ.get("WORKER_THREADS_COUNT", str(args.worker_threads_count)))

    o = None
    if api_key is not None:
        o=OrthancApiClient(url, headers={"api-key": api_key})
    else:
        o=OrthancApiClient(url, user=user, pwd=password)

    importer = OrthancFolderImporter(
        api_client=o,
        folder_path=folder_path,
        labels_list=labels_list,
        errors_path=errors_path,
        state_path=state_path,
        max_retries=max_retries,
        worker_threads_count=worker_threads_count
    )

    importer.execute()
