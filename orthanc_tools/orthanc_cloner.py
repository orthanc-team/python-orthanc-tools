import argparse
import logging
import os
from strenum import StrEnum

from orthanc_api_client import OrthancApiClient, ResourceType
from .scheduler import Scheduler
from .orthanc_monitor import OrthancMonitor, ChangeType

logger = logging.getLogger('orthanc_tools')


class ClonerMode(StrEnum):

    DEFAULT = 'Default'             # download instance and reupload them in new orthanc
    PEERING = 'Peering'             # use peering between 2 orthancs
    TRANSFER = 'Transfer'           # use the transfer plugin accelerator between 2 orthancs


class OrthancCloner(OrthancMonitor):

    def __init__(self,
                 source: OrthancApiClient,
                 destination: OrthancApiClient = None,          # must be defined for DEFAULT mode
                 worker_threads_count: int = 1,
                 persist_status_path: str = None,
                 polling_interval: float = 1,
                 mode: ClonerMode = ClonerMode.DEFAULT,
                 destination_peer: str = None,                    # the 'alias' of the destination peer if declared in Orthanc.  It must be defined for PEERING and TRANSFER mode
                 scheduler: Scheduler = None,
                 max_retries: int = 5,
                 error_folder_path: str = None
        ):
        super().__init__(
            api_client=source,
            worker_threads_count=worker_threads_count,
            persist_status_path=persist_status_path,
            polling_interval=polling_interval,
            scheduler=scheduler,
            max_retries=max_retries,
            error_folder_path=error_folder_path
        )

        self._destination = destination
        self._destination_peer = destination_peer
        self._mode = mode

        if self._scheduler:
            logger.info("Night & Week-end mode Enabled : " + str(self._scheduler._run_only_at_night_and_weekend))

        logger.info("Migrating with {n} threads".format(n=self._worker_threads_count))

        if self._mode in [ClonerMode.PEERING, ClonerMode.TRANSFER]:
            if destination_peer is None:
                raise ValueError("'destination_peer' must be defined in PEERING or TRANSFER mode")
        if self._mode == ClonerMode.DEFAULT:
            if destination is None:
                raise ValueError("'destination' must be defined in DEFAULT mode")

        if self._mode in [ClonerMode.PEERING, ClonerMode.DEFAULT]:
            self.add_handler(ChangeType.NEW_INSTANCE, self.handle_new_instance)
        elif self._mode == ClonerMode.TRANSFER:
            self.add_handler(ChangeType.STABLE_STUDY, self.handle_stable_study)


    def handle_new_instance(self, change_id, instance_id, api_client):
        try:
            if self._mode == ClonerMode.DEFAULT:
                dicom = api_client.instances.get_file(instance_id)

                self._destination.upload(dicom)
                logger.info(f"{change_id}, copied instance {instance_id}")
            elif self._mode == ClonerMode.PEERING:
                api_client.peers.send(target_peer=self._destination_peer, resources_ids=instance_id)

        except Exception as ex:
            raise Exception(f"Error while cloning instance {instance_id}: {str(ex)}")


    def handle_stable_study(self, change_id, study_id, api_client):
        try:
            if self._mode == ClonerMode.TRANSFER:
                transfer_job = api_client.transfers.send(
                    target_peer=self._destination_peer,
                    resources_ids=study_id,
                    resource_type=ResourceType.STUDY
                )
                transfer_job.wait_completed(timeout=None)

            logger.info(f"{change_id} transfered study {study_id}")

        except Exception as ex:
            raise Exception(f"Error while transferring study {study_id}: {str(ex)}")

# examples:
# python orthanc_tools/orthanc_cloner.py --source_url=http://192.168.0.10:8042 --source_user=user --source_pwd=pwd --dest_url=http://192.168.0.10:8042 --dest_user=user --dest_pwd=pwd
# python orthanc_tools/orthanc_cloner.py --source_url=http://192.168.0.10:8042 --source_user=user --source_pwd=pwd --dest_peer=pacs  --mode=Transfer

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
    parser.add_argument('--dest_peer', type=str, default=None, help='Orthanc destination peer (peer alias in source Orthanc)')
    parser.add_argument('--mode', type=str, default=None, help='Cloner Mode (Default, Peering, Transfer)')
    parser.add_argument('--persist_state_path', type=str, default=None, help='File path where the state of the cloner will be saved (to resume later)')
    parser.add_argument('--worker_threads_count', type=int, default=1, help='Number of worker threads')
    parser.add_argument('--error_folder_path', type=str, default=None, help='Folder path where to store error reports')
    parser.add_argument('--max_retries', type=int, default=5, help='Number of retries in case of error')

    Scheduler.add_parser_arguments(parser)

    args = parser.parse_args()

    source_url = os.environ.get("SOURCE_URL", args.source_url)
    source_user = os.environ.get("SOURCE_USER", args.source_user)
    source_pwd = os.environ.get("SOURCE_PWD", args.source_pwd)
    dest_url = os.environ.get("DEST_URL", args.dest_url)
    dest_user = os.environ.get("DEST_USER", args.dest_user)
    dest_pwd = os.environ.get("DEST_PWD", args.dest_pwd)
    dest_peer = os.environ.get("DEST_PEER", args.dest_peer)
    mode = os.environ.get("MODE", args.mode)
    persist_state_path = os.environ.get("PERSIST_STATE_PATH", args.persist_state_path)
    worker_threads_count = int(os.environ.get("WORKER_THREADS_COUNT", str(args.worker_threads_count)))
    error_folder_path = os.environ.get("ERROR_FOLDER_PATH", args.error_folder_path)
    max_retries = os.environ.get("MAX_RETRIES", args.max_retries)

    scheduler = Scheduler.create_from_args_and_env_var(args)

    destination = None
    if dest_url:
        destination = OrthancApiClient(dest_url, user=dest_user, pwd=dest_pwd)

    cloner = OrthancCloner(
        source=OrthancApiClient(source_url, user=source_user, pwd=source_pwd),
        destination=destination,
        persist_status_path=persist_state_path,
        mode=mode,
        destination_peer=dest_peer,
        scheduler=scheduler,
        worker_threads_count=worker_threads_count,
        error_folder_path=error_folder_path,
        max_retries=max_retries
    )

    cloner.execute(existing_changes_only=False)



