import argparse
import logging
import os

from orthanc_api_client import OrthancApiClient
from .orthanc_monitor import OrthancMonitor, ChangeType

logger = logging.getLogger('orthanc_tools')


class OrthancCloner(OrthancMonitor):

    def __init__(self,
                 source: OrthancApiClient,
                 destination: OrthancApiClient,
                 workers_count: int = 1,
                 persist_status_path: str = None,
                 polling_interval: float = 1
                 ):
        super().__init__(
            api_client=source,
            workers_count=workers_count,
            persist_status_path=persist_status_path,
            polling_interval=polling_interval
        )

        self._destination = destination

        self.add_handler(ChangeType.NEW_INSTANCE, self.handle_new_instance)

    def handle_new_instance(self, instance_id, api_client):
        try:
            dicom = api_client.instances.get_file(instance_id)

            self._destination.upload(dicom)
            logger.info(f"copied instance {instance_id}")
            return True

        except Exception as ex:
            logger.error(f"Error while cloning instance {instance_id}: {str(ex)}")
            return False


# examples:
# python orthanc_tools/orthanc_cloner.py --source_url=http://192.168.0.10:8042 --source_user=user --source_pwd=pwd --dest_url=http://192.168.0.10:8042 --dest_user=user --dest_pwd=pwd

if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Clone the content of an Orthanc into another Orthanc')
    parser.add_argument('--source_url', type=str, default=None, help='Orthanc source url')
    parser.add_argument('--source_user', type=str, default=None, help='Orthanc source user name')
    parser.add_argument('--source_pwd', type=str, default=None, help='Orthanc source password')
    parser.add_argument('--dest_url', type=str, default=None, help='Orthanc destination url')
    parser.add_argument('--dest_user', type=str, default=None, help='Orthanc destination user name')
    parser.add_argument('--dest_pwd', type=str, default=None, help='Orthanc destination password')
    parser.add_argument('--persist_state_path', type=str, default=None, help='Path where the state of the cloner will be saved (to resume later)')
    args = parser.parse_args()

    source_url = os.environ.get("SOURCE_URL", args.source_url)
    source_user = os.environ.get("SOURCE_USER", args.source_user)
    source_pwd = os.environ.get("SOURCE_PWD", args.source_pwd)
    dest_url = os.environ.get("DEST_URL", args.dest_url)
    dest_user = os.environ.get("DEST_USER", args.dest_user)
    dest_pwd = os.environ.get("DEST_PWD", args.dest_pwd)
    persist_state_path = os.environ.get("PERSIST_STATE_PATH", args.persist_state_path)

    cloner = OrthancCloner(
        source=OrthancApiClient(source_url, user=source_user, pwd=source_pwd),
        destination=OrthancApiClient(dest_url, user=dest_user, pwd=dest_pwd),
        persist_status_path=persist_state_path
    )

    cloner.execute(existing_changes_only=False)



