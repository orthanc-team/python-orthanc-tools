import queue
import threading
import time
import os
import logging

from orthanc_api_client import OrthancApiClient, ChangeType
from .scheduler import Scheduler
logger = logging.getLogger('orthanc_tools')


class OrthancMonitor:
    """
    Monitor the /changes route and trigger callback when a new change is detected
    """

    def __init__(self, 
                 api_client: OrthancApiClient,
                 worker_threads_count: int = 1,
                 persist_status_path: str = None,
                 start_at_sequence_id: int = None,
                 polling_interval: float = 0.5,
                 scheduler: Scheduler = None,
                 max_retries: int = 5,
                 error_folder_path: str = None
    ):

        self._api_client = api_client
        self._changes_to_process = queue.Queue(worker_threads_count + 1)
        self._monitoring_thread = None
        self._worker_threads_count = worker_threads_count
        self._worker_threads = []
        self._is_running = False
        self._polling_interval = polling_interval
        self._handlers = {}
        self._persist_status_path = None
        self._persist_status_lock = threading.RLock()
        self._changes_id_being_processed = set()
        self._largest_processed_change_id = 0
        self._scheduler = scheduler
        self._error_folder_path = error_folder_path
        self._max_retries = max_retries

        if persist_status_path is not None:
            self._persist_status_path = persist_status_path
            self._start_at_sequence_id = self._read_status_from_file()

        elif start_at_sequence_id is not None:
            self._start_at_sequence_id = start_at_sequence_id
        else:
            self._start_at_sequence_id = 0
        

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def add_handler(self, change_type: ChangeType, callback):
        self._handlers[change_type] = callback

    def _read_status_from_file(self):
        try:
            with open(self._persist_status_path) as f:
                sequence_id = int(f.read())
        except (ValueError, FileNotFoundError):  # if can not read, start at 0
            logger.warning("Could not read sequence id from file, starting at 0")
            return 0

        logger.info(f"Starting at sequence id from file = {sequence_id}")
        return sequence_id

    def _mark_change_as_being_processed(self, sequence_id):
        if self._persist_status_path is None:
            return

        with self._persist_status_lock:
            logger.debug(f"marking change {sequence_id} as being processed")
            self._changes_id_being_processed.add(sequence_id)

    def _mark_change_as_processed(self, sequence_id):
        # note: this can be improved: if multiple workers are processing events, we might skip a few changes when restarting
        if self._persist_status_path is None:
            return
        
        with self._persist_status_lock:
            self._changes_id_being_processed.remove(sequence_id)

            self._largest_processed_change_id = max(self._largest_processed_change_id, sequence_id)
            if len(self._changes_id_being_processed) > 0:
                restart_at_sequence_id = min(self._changes_id_being_processed) - 1
                logger.debug(f"marking change {sequence_id} as processed, will restart at {restart_at_sequence_id}, changes being processed: " + ", ".join([str(c) for c in self._changes_id_being_processed]))
            else:
                restart_at_sequence_id = self._largest_processed_change_id
                logger.debug(f"marking change {sequence_id} as processed, will restart at {restart_at_sequence_id}")


            # first write to a temp file and then move the file to make the operation robust
            tmp = self._persist_status_path + ".tmp"
            try:
                with open(tmp, "wt") as f:
                    f.write(str(restart_at_sequence_id))
                os.replace(tmp, self._persist_status_path)  # this is an 'atomic' operation
            except OSError as ex:
                raise Exception(f"Could not write sequence id to file \"{ex.filename}\": {ex.strerror}")

    def start(self, existing_changes_only: bool=False):
        """
        Parameters:
            existing_changes_only: True to stop processing changes once all current changes have been processed
                                   False to continue monitoring for new changes
        """
        # create monitoring thread
        self._monitoring_thread = threading.Thread(
            target=self._monitor_changes,
            name='Monitoring Thread',
            args=(existing_changes_only, )
        )

        # create worker threads
        for thread_id in range(0, self._worker_threads_count):
            self._worker_threads.append(threading.Thread(
                target=self._process_changes,
                name=f"Worker Thread {thread_id}",
                args=(thread_id, )
            ))

        # start threads
        self._is_running = True
        self._monitoring_thread.start()
        for wt in self._worker_threads:
            wt.start()

    def stop(self):
        logger.info("Stopping Orthanc Monitor")

        # first stop the monitoring thread so we don't produce events anymore
        self._is_running = False
        self._monitoring_thread.join()

        # post one 'empty' exit message per thread to unlock the threads from waiting on the process queue
        for i in range(0, self._worker_threads_count):
            self._changes_to_process.put(None)

        for t in self._worker_threads:
            t.join()

    def _monitor_changes(self, existing_changes_only):
        logger.debug(f"Starting Monitoring thread at change id = {self._start_at_sequence_id}")

        last_sequence_id = self._start_at_sequence_id
        done = False

        while self._is_running:
            if existing_changes_only and done:
                self._is_running = False
                return

            done = False
            while not done and self._is_running: # read as fast as you can while there are still events

                if self._scheduler:
                    self._scheduler.wait_right_time_to_run(logger=logger)

                # get the list of changes from orthanc
                try:
                    changes, last_sequence_id, done = self._api_client.get_changes(
                        since=last_sequence_id,
                        limit=100
                    )
                except Exception as ex:
                    logger.warning("Could not reach Orthanc, retrying ...")
                    break

                # enqueue the events
                for change in changes:
                    self._mark_change_as_being_processed(change.sequence_id)
                    self._changes_to_process.put(change)  # if the queue is full, this will block until there's a free slot

            # if no events available, wait and poll again
            time.sleep(self._polling_interval)

    def _process_changes(self, worker_id):
        logger.debug(f"Starting Processing thread {worker_id}")

        while True:
            change = self._changes_to_process.get()  # block until a message is available

            if change is None:  # sent by stop() to stop all worker threads
                self._changes_to_process.task_done()
                break

            retries = 0
            retry_delays = [5, 20, 60, 300, 900, 1800, 3600, 7200]
            processed = False
            last_error = None

            while not processed and retries <= min(self._max_retries, len(retry_delays)):
                if retries >= 1:
                    delay = retry_delays[retries - 1]
                    logger.info(f"waiting {delay} seconds before retrying change {change.sequence_id} {change.change_type}")
                    time.sleep(delay)

                try:
                    # process events (this is blocking the worker thread until the handler returns)
                    if change.change_type in self._handlers:
                        logger.debug(f"processing change {change.sequence_id} {change.change_type}")
                        self._handlers[change.change_type](change.sequence_id, change.resource_id, self._api_client)
                        processed = True
                    else:
                        logger.debug(f"not processing change {change.sequence_id} {change.change_type}")
                        processed = True  # but we consider it has been processed not to handle it after a restart

                except Exception as ex:
                    logger.exception("Unhandled exception in event handler: ", ex)
                    last_error = str(ex)

                retries = retries + 1


            if not processed and self._error_folder_path:
                error_file_path = os.path.join(self._error_folder_path, f"{change.sequence_id:010d}." + str(change.change_type) + ".error.txt")
                try:
                    with open(error_file_path, "wt") as f:
                        f.write(last_error)
                except OSError as ex:
                    raise Exception(f"Could not write error report to file \"{ex.filename}\": {ex.strerror}")
                # if we store errors on disk, we consider that the change has been processed since we keep a track of its failure -> it will not be handled again after a restart
                processed = True

            if processed:
                self._mark_change_as_processed(change.sequence_id)

            self._changes_to_process.task_done()  # tell the queue the item has been processed

        logger.debug("Processing thread stopped")


    def execute(self, existing_changes_only: bool = True):
        """
        Parameters:
            existing_changes_only: True to stop processing changes once all current changes have been processed
                                   False to continue monitoring for new changes
        """

        self.start(existing_changes_only=existing_changes_only)

        if existing_changes_only:
            while self._is_running:
                time.sleep(self._polling_interval)
            self.stop()
