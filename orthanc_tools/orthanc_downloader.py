import time, sys
import argparse
import logging
from orthanc_api_client import OrthancApiClient
import os

# examples:
# python orthanc_tools/orthanc_downloader.py --folder=./backup --url=http://192.168.0.10:8042 --user=user --password=pwd --labels=label1,label2


logger = logging.getLogger(__name__)

if __name__ == '__main__':
    level = logging.INFO
    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Download the content of Orthanc in a folder, according to the labels')
    parser.add_argument('--url', type=str, default='http://localhost:8042', help='Orthanc url')
    parser.add_argument('--user', type=str, default=None, help='Orthanc user name')
    parser.add_argument('--password', type=str, default=None, help='Orthanc password')
    parser.add_argument('--api_key', type=str, default=None, help='Orthanc api-key')
    parser.add_argument('--folder', type=str, help='Folder to store the DICOM files to.')
    parser.add_argument('--labels', type=str, default=None, help='Comma separated list of labels. Only studies with these labels will be downloaded.')
    args = parser.parse_args()

    o = None
    if args.api_key is not None:
        o=OrthancApiClient(args.url, headers={"api-key":args.api_key})
    else:
        o=OrthancApiClient(args.url, user=args.user, pwd=args.password)

    labels = []
    # labels args present, download only these ones
    if args.labels is not None:
        labels = args.labels.split(',')

    retry_count = 0
    retry_delays = [5, 20, 60, 300, 900]

    studies_ids = []
    while retry_count < 5:
        if retry_count >= 1:
            delay = retry_delays[retry_count - 1]
            logger.info(f"waiting {delay} seconds before retrying get studies ids")
            time.sleep(delay)
        try:
            logger.info(f"Getting list of studies ids...")
            # workaround to avoid find results limit
            all_ids = o.studies.get_all_ids()
            for id in all_ids:
                study_labels = o.studies.get_labels(id)
                if any(element in study_labels for element in labels):
                    studies_ids.append(id)
            break
        except Exception as ex:
            retry_count += 1
            if retry_count == 5:
                logger.error(f"Error (retried 5 times) while getting studies ids. Ex: {str(ex)}")
                sys.exit(1)
            else:
                logger.warning(f"Error while getting studies ids, retrying... Ex:{str(ex)}")

    progress_counter = 1
    for id in studies_ids:
        try:
            logger.info(f"Downloading study {progress_counter} out of {len(studies_ids)}")
            folder_path = args.folder + id
            os.mkdir(folder_path)
            o.studies.download_instances(study_id=id, path=folder_path)
            progress_counter += 1
        except Exception as ex:
            logger.error(f"Error during download for study {id}. Ex: {str(ex)}")
            sys.exit(1)

    logger.info("Over :-)")