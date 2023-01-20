import unittest, os, glob
import hl7  # https://python-hl7.readthedocs.org/en/latest/
import pydicom
from orthanc_tools import DicomWorklistBuilder
import tempfile
import time

class MyDicomWorklistBuilder(DicomWorklistBuilder):

    def customize(self, ds: pydicom.dataset.FileDataset) -> pydicom.dataset.FileDataset:
        ds.StudyInstanceUID = ds.StudyInstanceUID[:60]
        return ds


class TestDicomWorklistBuilder(unittest.TestCase):

    def test_customize(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            builder = MyDicomWorklistBuilder(temporary_dir)
            values = {
                "AccessionNumber" : "1",
                "PatientID" : "2",
                "PatientName" : "3",
                "PatientBirthDate" : "",
                "PatientSex": "",
                "RequestedProcedureID": "2",
                "SpecificCharacterSet": "ISO_IR 100",
                "ScheduledStationAETitle": "TOTO",
                "ScheduledProcedureStepID": "5"
            }
            filename = builder.generate(values = values)

            wl_readback = pydicom.read_file(filename)
            self.assertEqual(60, len(wl_readback.StudyInstanceUID))
            self.assertEqual("2", wl_readback.PatientID)
