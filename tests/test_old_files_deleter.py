from unittest import TestCase
from orthanc_tools import OldFilesDeleter
import os
import tempfile
import time
from pathlib import Path
from orthanc_tools.helpers.time_out import TimeOut

class TestOldFilesDeleter(TestCase):

    def test_execute_once(self):

        with tempfile.TemporaryDirectory() as temp_dir:

            # create 2 files
            txt_file_path = os.path.join(temp_dir, 'file.txt')
            Path(txt_file_path).touch()
            bin_file_path = os.path.join(temp_dir, 'file.bin')
            Path(bin_file_path).touch()

            # wait 0.2 seconds
            time.sleep(0.2)

            # ask a fileDeleter to delete all files older than 0.1 seconds
            OldFilesDeleter(folder_to_monitor = temp_dir,
                            timeout = 0.1,
                            filter = '*.txt',
                            recursive = False).execute_once()

            # make sure only the .txt file has been deleted
            self.assertFalse(os.path.exists(txt_file_path))
            self.assertTrue(os.path.exists(bin_file_path))

    def test_recursive(self):

        with tempfile.TemporaryDirectory() as temp_dir:
            sub_dir_path = os.path.join(temp_dir, 'subdir')
            os.mkdir(sub_dir_path)

            # create 2 files at root, one in a subfolder
            txt_file_path = os.path.join(temp_dir, 'file.txt')
            Path(txt_file_path).touch()
            bin_file_path = os.path.join(temp_dir, 'file.bin')
            Path(bin_file_path).touch()
            sub_txt_file_path = os.path.join(sub_dir_path, 'file.txt')
            Path(sub_txt_file_path).touch()

            # wait 0.2 seconds
            time.sleep(0.2)

            # ask a fileDeleter to delete all files older than 0.1 seconds
            OldFilesDeleter(folder_to_monitor = temp_dir,
                            timeout = 0.1,
                            filter = '*.txt',
                            recursive = True).execute_once()

            # make sure only the .txt file has been deleted including the one in the subfolder
            self.assertFalse(os.path.exists(txt_file_path))
            self.assertFalse(os.path.exists(sub_txt_file_path))
            self.assertTrue(os.path.exists(bin_file_path))

    def test_not_recursive(self):

        with tempfile.TemporaryDirectory() as tempDir:
            sub_dir_path = os.path.join(tempDir, 'subdir')
            os.mkdir(sub_dir_path)

            # create 2 files at root, one in a subfolder
            txt_file_path = os.path.join(tempDir, 'file.txt')
            Path(txt_file_path).touch()
            bin_file_path = os.path.join(tempDir, 'file.bin')
            Path(bin_file_path).touch()
            sub_txt_file_path = os.path.join(sub_dir_path, 'file.txt')
            Path(sub_txt_file_path).touch()

            # wait 0.2 seconds
            time.sleep(0.2)

            # ask a fileDeleter to delete all files older than 0.1 seconds
            OldFilesDeleter(folder_to_monitor = tempDir,
                            timeout = 0.1,
                            filter = '*.txt',
                            recursive = False).execute_once()

            # make sure only the .txt file at the root has been deleted
            self.assertFalse(os.path.exists(txt_file_path))
            self.assertTrue(os.path.exists(sub_txt_file_path))
            self.assertTrue(os.path.exists(bin_file_path))

    def test_thread(self):

        with tempfile.TemporaryDirectory() as temp_dir:

            with OldFilesDeleter(folder_to_monitor = temp_dir,
                                 timeout = 0.1,
                                 filter = '*.txt',
                                 execution_interval = 0.05) as fileDeleter:

                # create 1 file
                txt_file_path = os.path.join(temp_dir, 'file.txt')
                Path(txt_file_path).touch()

                # wait at least 0.2 seconds
                time.sleep(0.2)
                # also make sure the deleter has run at least once
                TimeOut.wait_until_condition(lambda: fileDeleter._execution_count >= 1, timeout = 5.0, evaluate_interval = 0.1)

                # make sure it has been deleted
                self.assertFalse(os.path.exists(txt_file_path))
