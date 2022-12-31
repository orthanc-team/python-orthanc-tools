from unittest import TestCase
from orthanc_tools import OldFilesDeleter
import os
import tempfile
import time
from pathlib import Path
from orthanc_tools.time_out import TimeOut

class TestOldFilesDeleter(TestCase):

    def test_execute_once(self):

        with tempfile.TemporaryDirectory() as tempDir:

            # create 2 files
            txtFilePath = os.path.join(tempDir, 'file.txt')
            Path(txtFilePath).touch()
            binFilePath = os.path.join(tempDir, 'file.bin')
            Path(binFilePath).touch()

            # wait 0.2 seconds
            time.sleep(0.2)

            # ask a fileDeleter to delete all files older than 0.1 seconds
            OldFilesDeleter(folder_to_monitor = tempDir,
                            timeout = 0.1,
                            filter = '*.txt',
                            recursive = False).execute_once()

            # make sure only the .txt file has been deleted
            self.assertFalse(os.path.exists(txtFilePath))
            self.assertTrue(os.path.exists(binFilePath))

    def test_recursive(self):

        with tempfile.TemporaryDirectory() as tempDir:
            subDirPath = os.path.join(tempDir, 'subdir')
            os.mkdir(subDirPath)

            # create 2 files at root, one in a subfolder
            txtFilePath = os.path.join(tempDir, 'file.txt')
            Path(txtFilePath).touch()
            binFilePath = os.path.join(tempDir, 'file.bin')
            Path(binFilePath).touch()
            subTxtFilePath = os.path.join(subDirPath, 'file.txt')
            Path(subTxtFilePath).touch()

            # wait 0.2 seconds
            time.sleep(0.2)

            # ask a fileDeleter to delete all files older than 0.1 seconds
            OldFilesDeleter(folder_to_monitor = tempDir,
                            timeout = 0.1,
                            filter = '*.txt',
                            recursive = True).execute_once()

            # make sure only the .txt file has been deleted including the one in the subfolder
            self.assertFalse(os.path.exists(txtFilePath))
            self.assertFalse(os.path.exists(subTxtFilePath))
            self.assertTrue(os.path.exists(binFilePath))

    def test_not_recursive(self):

        with tempfile.TemporaryDirectory() as tempDir:
            subDirPath = os.path.join(tempDir, 'subdir')
            os.mkdir(subDirPath)

            # create 2 files at root, one in a subfolder
            txtFilePath = os.path.join(tempDir, 'file.txt')
            Path(txtFilePath).touch()
            binFilePath = os.path.join(tempDir, 'file.bin')
            Path(binFilePath).touch()
            subTxtFilePath = os.path.join(subDirPath, 'file.txt')
            Path(subTxtFilePath).touch()

            # wait 0.2 seconds
            time.sleep(0.2)

            # ask a fileDeleter to delete all files older than 0.1 seconds
            OldFilesDeleter(folder_to_monitor = tempDir,
                            timeout = 0.1,
                            filter = '*.txt',
                            recursive = False).execute_once()

            # make sure only the .txt file at the root has been deleted
            self.assertFalse(os.path.exists(txtFilePath))
            self.assertTrue(os.path.exists(subTxtFilePath))
            self.assertTrue(os.path.exists(binFilePath))

    def test_thread(self):

        with tempfile.TemporaryDirectory() as tempDir:

            with OldFilesDeleter(folder_to_monitor = tempDir,
                                 timeout = 0.1,
                                 filter = '*.txt',
                                 execution_interval = 0.05) as fileDeleter:

                # create 1 file
                txtFilePath = os.path.join(tempDir, 'file.txt')
                Path(txtFilePath).touch()

                # wait at least 0.2 seconds
                time.sleep(0.2)
                # also make sure the deleter has run at least once
                TimeOut.wait_until_condition(lambda: fileDeleter._execution_count >= 1, timeout = 5.0, evaluate_interval = 0.1)

                # make sure it has been deleted
                self.assertFalse(os.path.exists(txtFilePath))
