import os
import time
import unittest
import hl7  # https://python-hl7.readthedocs.org/en/latest/
from orthanc_tools import hl7Lib
import re
import shutil
from orthanc_tools import Hl7FolderMonitor
import tempfile
from orthanc_api_client import helpers
from orthanc_tools import Hl7WorklistParserVetera, DicomWorklistBuilder, Hl7OrmWorklistMsgHandler
import pathlib

here = pathlib.Path(__file__).parent.resolve()

def hl7_echo_message_handler(incoming_hl7_message: str) -> hl7.Message:
    """
    This is a 'stupid' handler that just repeats the message it receives (useful for testing)
    """
    pass
    return hl7.parse(incoming_hl7_message)


class TestHl7FolderMonitor(unittest.TestCase):

    def test_start_and_stop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = Hl7FolderMonitor(temp_dir, {
            }, 5)

            # just make sure we can start/stop the server
            self.assertFalse(monitor.is_running())

            monitor.start()
            self.assertTrue(monitor.is_running())

            monitor.stop()
            self.assertFalse(monitor.is_running())

    def test_callback_and_deletion(self):
        # start a monitor that will check the folder and delete the file after the callback
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = Hl7FolderMonitor(temp_dir, {'ORM^O01': hl7_echo_message_handler}, 3)

            # validate that ORM^O01 messages has been received
            hl7_str = r"MSH|^~\&|TOTO|TUTU|SOFTNAME|CHABC|201602011049||ORM^O01|exp_ANE_5|P|2.3.1" + "\rPID|1||8123456DK01||DUPONT^ALBERT ANTHONY|||||||||||||123456"

            file_path = temp_dir + "/test.hl7"
            f = open(file_path, "w")
            f.write(hl7_str)
            f.close()
            self.assertEqual(1, len(os.listdir(temp_dir)))

            monitor.start()

            # wait until the file has been deleted
            helpers.wait_until(lambda: len(os.listdir(temp_dir)) == 0, 4)
            self.assertEqual(0, len(os.listdir(temp_dir)))
            monitor.stop()

    def test_worklist_creation(self):
        # start a monitor that will check the folder and create the wl file
        with tempfile.TemporaryDirectory() as temp_dir_hl7:
            with tempfile.TemporaryDirectory() as temp_dir_wl:
                orm_parser = Hl7WorklistParserVetera()
                worklist_builder = DicomWorklistBuilder(folder=temp_dir_wl)
                orm_handler = Hl7OrmWorklistMsgHandler(parser=orm_parser, builder=worklist_builder)

                monitor = Hl7FolderMonitor(temp_dir_hl7, {'ORM^O01': orm_handler.handle_orm_message}, 3)

                # we use `\r\n` as newline delimiter because this how Vetera works...
                # plus TF-8 Byte Order Mark (BOM) (EF BB BF bytes) at the beginning
                # plus the ä in the description (C3 A4)
                hl7_str = b"\xef\xbb\xbfMSH|^~\\&|VETERA|VETERA|conquest|conquest|20170731081517||ORM^O01|1000000001|P|2.5.0|||||\r\n"\
                    b"PID|1|999888777||123456789012345|GP.Software^Vetera||20070501|F|||||||||||||||||||||||||||Katze|Balinese|ALTERED|ZH-123|\r\n"\
                    b"ORC|NW||||||||20170731081517||||||||||\r\n"\
                    b"OBR|||1000000001|\xc3\xa4||20170731081517|||||||||||||||DX|||ZUG||||||||Dr. P. Muster||||\r\n"

                file_path = temp_dir_hl7 + "/test.hl7"
                f = open(file_path, "wb")
                f.write(hl7_str)
                f.close()

                self.assertEqual(1, len(os.listdir(temp_dir_hl7)))

                monitor.start()

                # wait until the hl7 file has been deleted, so that, the wl file should have been created
                helpers.wait_until(lambda: len(os.listdir(temp_dir_hl7)) == 0, 4)

                self.assertEqual(1, len(os.listdir(temp_dir_wl)))
                monitor.stop()

    def test_worklist_creation2(self):
        # start a monitor that will check the folder and create the wl file
        with tempfile.TemporaryDirectory() as temp_dir_hl7:
            with tempfile.TemporaryDirectory() as temp_dir_wl:
                orm_parser = Hl7WorklistParserVetera()
                worklist_builder = DicomWorklistBuilder(folder=temp_dir_wl)
                orm_handler = Hl7OrmWorklistMsgHandler(parser=orm_parser, builder=worklist_builder)

                monitor = Hl7FolderMonitor(temp_dir_hl7, {'ORM^O01': orm_handler.handle_orm_message}, 3)

                # regular `\r`
                hl7_str = r"MSH|^~\&|VETERA|VETERA|conquest|conquest|20170731081517||ORM^O01|1000000001|P|2.5.0|||||" + "\r"\
                    "PID|1|999888777||123456789012345|GP.Söftware^Vetera||20070501|F|||||||||||||||||||||||||||Katze|Balinese|ALTERED|ZH-123|\r"\
                    "ORC|NW||||||||20170731081517||||||||||\r"\
                    "OBR|||1000000001|HD||20170731081517|||||||||||||||DX|||ZUG||||||||Dr. P. Muster||||\r"

                file_path = temp_dir_hl7 + "/test.hl7"
                f = open(file_path, "w")
                f.write(hl7_str)
                f.close()

                self.assertEqual(1, len(os.listdir(temp_dir_hl7)))

                monitor.start()

                # wait until the hl7 file has been deleted, so that, the wl file should have been created
                helpers.wait_until(lambda: len(os.listdir(temp_dir_hl7)) == 0, 4)

                self.assertEqual(1, len(os.listdir(temp_dir_wl)))
                monitor.stop()

    def test_worklist_creation_carriage_return(self):
        # start a monitor that will check the folder and create the wl file
        # some messages from Vetera contains a carriage return in the middle of a segment...

        with tempfile.TemporaryDirectory() as temp_dir_hl7:
            with tempfile.TemporaryDirectory() as temp_dir_wl:
                orm_parser = Hl7WorklistParserVetera()
                worklist_builder = DicomWorklistBuilder(folder=temp_dir_wl)
                orm_handler = Hl7OrmWorklistMsgHandler(parser=orm_parser, builder=worklist_builder)

                hl7_folder_source = here / "stimuli"

                for file in os.listdir(hl7_folder_source):
                    if file == "carriage-return.hl7":
                        src_file = os.path.join(hl7_folder_source, file)
                        if os.path.isfile(src_file):
                            shutil.copy2(src_file, temp_dir_hl7)

                monitor = Hl7FolderMonitor(temp_dir_hl7, {'ORM^O01': orm_handler.handle_orm_message}, 3)

                monitor.start()

                # wait until the hl7 file has been deleted, so that, the wl file should have been created
                helpers.wait_until(lambda: len(os.listdir(temp_dir_hl7)) == 0, 4)

                self.assertEqual(1, len(os.listdir(temp_dir_wl)))
                monitor.stop()

    def test_worklist_creation_missing_birthdate(self):
        # start a monitor that will check the folder and create the wl file (which will fail)
        # some messages from Vetera does not contain a birthdate...

        with tempfile.TemporaryDirectory() as temp_dir_hl7:
            with tempfile.TemporaryDirectory() as temp_dir_wl:
                orm_parser = Hl7WorklistParserVetera()
                worklist_builder = DicomWorklistBuilder(folder=temp_dir_wl)
                orm_handler = Hl7OrmWorklistMsgHandler(parser=orm_parser, builder=worklist_builder)

                hl7_folder_source = here / "stimuli"

                for file in os.listdir(hl7_folder_source):
                    if file == "missing-birthdate.hl7":
                        src_file = os.path.join(hl7_folder_source, file)
                        if os.path.isfile(src_file):
                            shutil.copy2(src_file, temp_dir_hl7)

                monitor = Hl7FolderMonitor(temp_dir_hl7, {'ORM^O01': orm_handler.handle_orm_message}, 3)

                monitor.start()

                # wait until the hl7 file has been deleted, so that, the wl file should have been created
                helpers.wait_until(lambda: len(os.listdir(temp_dir_hl7)) == 0, 4)

                self.assertEqual(0, len(os.listdir(temp_dir_wl)))
                monitor.stop()

    def test_error_and_stop(self):
        # start a monitor that will check a non-existing folder and then stop
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = Hl7FolderMonitor(temp_dir + "/unknown-folder/", {'ORM^O01': hl7_echo_message_handler}, 3)

            hl7_str = r"MSH|^~\&|TOTO|TUTU|SOFTNAME|CHABC|201602011049||ORM^O01|exp_ANE_5|P|2.3.1" + "\rPID|1||8123456DK01||DUPONT^ALBERT ANTHONY|||||||||||||123456"

            file_path = temp_dir + "/test.hl7"
            f = open(file_path, "w")
            f.write(hl7_str)
            f.close()
            self.assertEqual(1, len(os.listdir(temp_dir)))

            monitor.start()

            # wait until the monitor stops because the monitored folder doesn't exist
            helpers.wait_until(lambda: monitor.is_running() is False, 4)
            self.assertFalse(monitor.is_running())
            monitor.stop()