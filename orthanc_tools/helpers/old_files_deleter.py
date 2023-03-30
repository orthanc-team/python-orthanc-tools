import typing
import time
import glob
import os
from .time_out import TimeOut
import threading
import logging

logger = logging.getLogger(__name__)


class OldFilesDeleter:
    """
    removes files that are older than a certain age (usefull, i.e, to remove worklists that are too old
    """

    def __init__(self, folder_to_monitor: str, timeout: float = 24*3600.0, filter: str = "*", execution_interval: float = 1*3600.0, recursive: bool = True):
        """
        :param folder_to_monitor: the folder to monitor
        :param timeout: the age (in seconds) after which the file shall be deleted
        :param filter: a filter to filter the files to be monitored by the Deleter
        :param execution_interval: the delay between two executions
        :param recursive: explore subfolders too
        """
        self._folder_to_monitor = folder_to_monitor
        self._timeout = timeout
        self._filter = filter
        self._execution_interval = execution_interval
        self._recursive = recursive
        self._thread = None
        self._execution_count = 0 # mainly used in unit tests

    def execute_once(self):
        self._execution_count += 1

        deleted_file_counter = 0
        oldest_time = time.time() - self._timeout

        glob_filter = os.path.join(self._folder_to_monitor, self._filter)
        if self._recursive:
            glob_filter = os.path.join(self._folder_to_monitor, '**/', self._filter)

        for file_path in glob.glob(glob_filter, recursive = self._recursive):
            last_modification_time = os.path.getmtime(file_path)
            if last_modification_time < oldest_time:
                logger.debug("deleting {file_path}".format(file_path = file_path))
                os.unlink(file_path)
                deleted_file_counter += 1

        logger.info("deleted {n} old file(s)".format(n = deleted_file_counter))

    def execute(self):
        self._is_running = True
        timeout = TimeOut(self._execution_interval)

        # execute once at startup and then every X
        self.execute_once()

        while self._is_running:
            timeout.wait_until_expired()
            self.execute_once()
            timeout.reset()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        logger.info("Starting old files deleter ({folder})".format(folder = self._folder_to_monitor))

        # create monitoring thread
        self._thread = threading.Thread(
            target = self.execute,
            name = 'OldFilesDeleter Thread'
        )
        self._thread.start()

    def stop(self):
        logger.info("Stopping old files deleter ({folder})".format(folder = self._folder_to_monitor))
        self._is_running = False
        self._thread.join()