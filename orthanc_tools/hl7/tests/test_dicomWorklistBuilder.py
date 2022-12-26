import unittest, os, glob
import hl7  # https://python-hl7.readthedocs.org/en/latest/
import pydicom
from hl7Lib import DicomWorklistBuilder
import tempfile
import time

class MyDicomWorklistBuilder(DicomWorklistBuilder):

    def customize(self, ds: pydicom.dataset.FileDataset) -> pydicom.dataset.FileDataset:
        ds.StudyInstanceUID = ds.StudyInstanceUID[:60]
        return ds


class TestDicomWorklistBuilder(unittest.TestCase):

    def testCustomize(self):
        with tempfile.TemporaryDirectory() as temporaryDir:
            builder = MyDicomWorklistBuilder(temporaryDir)
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

            wlReadback = pydicom.read_file(filename)
            self.assertEqual(60, len(wlReadback.StudyInstanceUID))
            self.assertEqual("2", wlReadback.PatientID)
