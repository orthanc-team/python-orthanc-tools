import argparse
import logging
from orthanc_api_client import OrthancApiClient

# examples:
# python orthanc_tools/orthanc_folder_importer.py --folder=./tests/stimuli --url=http://192.168.0.10:8042 --user=user --password=pwd --skip=.txt,.ini


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Import the content of a folder in Orthanc')
    parser.add_argument('--url', type=str, default='http://localhost:8042', help='Orthanc url')
    parser.add_argument('--user', type=str, default=None, help='Orthanc user name')
    parser.add_argument('--password', type=str, default=None, help='Orthanc password')
    parser.add_argument('--folder', type=str, help='Folder to import')
    parser.add_argument('--skip_extensions', type=str, default='', help='comma separated list of extensions to ignore: ex .zip,.cne')
    args = parser.parse_args()

    o = OrthancApiClient(args.url, user=args.user, pwd=args.password)
    o.upload_folder(
        folder_path=args.folder, 
        skip_extensions=args.skip_extensions.split(','),
        ignore_errors=True)
