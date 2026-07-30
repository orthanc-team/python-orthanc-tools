import os
import tempfile
import unittest
from unittest import mock

import hl7
import pydicom

from orthanc_tools.hl7Lib.hl7_client import MLLPClient
from orthanc_tools.hl7Lib.hl7_dicom_worklist_builder import DicomWorklistBuilder
from orthanc_tools.hl7Lib.hl7_orm_worklist_msg_handler import Hl7OrmWorklistMsgHandler
from orthanc_tools.hl7Lib.hl7_oru_report_msg_handler import Hl7OruReportMsgHandler
from orthanc_tools.hl7Lib.hl7_server import handle_error_message


ORM_MESSAGE = (
    r"MSH|^~\&|SENDER|FACILITY|RECEIVER|DESTINATION|20260730120000||"
    "ORM^O01|orm-message-id|P|2.3\rPID|1"
)
ORU_MESSAGE = (
    r"MSH|^~\&|SENDER|FACILITY|RECEIVER|DESTINATION|20260730120000||"
    "ORU^R01|oru-message-id|P|2.3\rPID|1"
)


class FakeParser:
    def __init__(self, result=None, error=None):
        self._result = result or {}
        self._error = error

    def parse(self, hl7_message):
        if self._error:
            raise self._error
        return self._result


class FakeBuilder:
    _folder = "unused"
    _orthanc_client = None

    def __init__(self, error=None):
        self._error = error

    def generate(self, values):
        if self._error:
            raise self._error
        return "generated"


class TestHl7Acknowledgements(unittest.TestCase):
    def test_orm_success_acknowledgement_has_formatted_header(self):
        handler = Hl7OrmWorklistMsgHandler(
            parser=FakeParser(),
            builder=FakeBuilder(),
        )

        response = handler.handle_orm_message(ORM_MESSAGE)

        self.assertEqual("AA", response["MSA.F1.R1"])
        self.assertEqual("orm-message-id", response["MSA.F2.R1"])
        self.assertEqual("RECEIVER", response["MSH.F3.R1"])
        self.assertEqual("ACK", response["MSH.F9.R1.C1"])
        self.assertEqual("O01", response["MSH.F9.R1.C2"])
        self.assertNotIn("{sending_application}", str(response))

    def test_orm_parser_failure_returns_application_error(self):
        handler = Hl7OrmWorklistMsgHandler(
            parser=FakeParser(error=ValueError("invalid order")),
            builder=FakeBuilder(),
        )

        response = handler.handle_orm_message(ORM_MESSAGE)

        self.assertEqual("AE", response["MSA.F1.R1"])
        self.assertEqual("invalid order", response["MSA.F3.R1"])

    def test_orm_builder_failure_returns_application_error(self):
        handler = Hl7OrmWorklistMsgHandler(
            parser=FakeParser(),
            builder=FakeBuilder(error=RuntimeError("disk full")),
        )

        response = handler.handle_orm_message(ORM_MESSAGE)

        self.assertEqual("AE", response["MSA.F1.R1"])
        self.assertEqual("disk full", response["MSA.F3.R1"])

    def test_oru_parser_failure_returns_application_error_for_r01(self):
        handler = Hl7OruReportMsgHandler(
            parser=FakeParser(error=ValueError("invalid report")),
            builder=FakeBuilder(),
        )

        response = handler.handle_oru_message(ORU_MESSAGE)

        self.assertEqual("AE", response["MSA.F1.R1"])
        self.assertEqual("ACK", response["MSH.F9.R1.C1"])
        self.assertEqual("R01", response["MSH.F9.R1.C2"])

    def test_default_error_handler_is_directly_callable(self):
        response = handle_error_message(
            ORM_MESSAGE,
            error_description="unsupported | message",
        )

        self.assertEqual("AR", response["MSA.F1.R1"])
        self.assertEqual("unsupported | message", response["MSA.F3.R1"])


class TestMllpClientWrites(unittest.TestCase):
    def test_send_uses_sendall(self):
        client = object.__new__(MLLPClient)
        client.encoding = "iso-8859-1"
        client.sb = b"\x0b"
        client.eb = b"\x1c"
        client.cr = b"\r"
        client.socket = mock.Mock()
        client._receive = mock.Mock(return_value="response")
        message = hl7.parse(ORM_MESSAGE)

        self.assertEqual("response", client.send(message))

        client.socket.sendall.assert_called_once()
        client.socket.send.assert_not_called()


class TestWorklistFileSafety(unittest.TestCase):
    @staticmethod
    def _values(accession_number):
        return {
            "AccessionNumber": accession_number,
            "PatientID": "patient",
            "PatientName": "Patient^Test",
            "PatientBirthDate": "20000101",
            "PatientSex": "O",
            "RequestedProcedureID": "procedure",
            "SpecificCharacterSet": "ISO_IR 100",
            "ScheduledStationAETitle": "ORTHANC",
            "ScheduledProcedureStepID": "step",
        }

    def test_accession_number_cannot_escape_worklist_folder(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            builder = DicomWorklistBuilder(folder=temporary_dir)

            file_name = builder.generate(self._values("../outside"))

            self.assertEqual(
                os.path.realpath(temporary_dir),
                os.path.dirname(os.path.realpath(file_name)),
            )
            self.assertTrue(os.path.isfile(file_name))
            self.assertFalse(os.path.exists(os.path.join(temporary_dir, "..", "outside.wl")))

    def test_failed_write_does_not_leave_partial_file(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            builder = DicomWorklistBuilder(folder=temporary_dir)

            with mock.patch.object(
                pydicom.dataset.FileDataset,
                "save_as",
                side_effect=RuntimeError("write failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "write failed"):
                    builder.generate(self._values("safe-accession"))

            self.assertEqual([], os.listdir(temporary_dir))


if __name__ == "__main__":
    unittest.main()
