import unittest, os, glob
import hl7  # https://python-hl7.readthedocs.org/en/latest/
import pydicom
from pydicom import dcmread
from orthanc_tools import DicomWorklistBuilder
import tempfile
from orthanc_api_client import OrthancApiClient
import pathlib
import subprocess

here = pathlib.Path(__file__).parent.resolve().parent.resolve().parent.resolve().parent.resolve()


class TestDicomWorklistBuilder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"tests/docker-setup")
        subprocess.run(["docker", "compose", "up", "-d"], cwd=here/"tests/docker-setup")

        cls.oa = OrthancApiClient('http://localhost:10042', user='test', pwd='test')
        cls.oa.wait_started()

        cls.ob = OrthancApiClient('http://localhost:10043', user='test', pwd='test')
        cls.ob.wait_started()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"tests/docker-setup")


    def test_generate_with_orthanc_client(self):
        self.oa.worklists.delete_all()
        self.ob.worklists.delete_all()

        o = OrthancApiClient('http://localhost:10042', user='test', pwd='test')
        builder = DicomWorklistBuilder(orthanc_client=o)

        values = {
            'AccessionNumber': '3264557',
            'IssuerOfPatientID': 'ECSIMAGING',
            'Modality': 'NMR',
            'OrderFillerIdentifierSequence': '3264557^ECSIMAGING',
            'OrderPlacerIdentifierSequence': '3264557',
            'OtherPatientIDs': '',
            'PatientAddress': '2 rue ^^THUIR^^66300^^H',
            'PatientBirthDate': '19550812',
            'PatientID': '5343197',
            'PatientName': 'LLOxxx^Simxxx^^^',
            'PatientSex': 'F',
            'ReferringPhysicianName': 'Docteur^Traitant',
            'RequestedProcedureDescription': 'IRM FOIE IV',
            'RequestedProcedureID': '3264557',
            'RequestingPhysician': 'Docteur^Quenotte',
            'SOPInstanceUID': '1.2.826.0.1.3680043.8.498.59927963937066647984484704740995616579',
            'ScheduledPerformingPhysicianName': None,
            'ScheduledProcedureStepID': '3264557',
            'ScheduledProcedureStepStartDate': '20201001',
            'ScheduledProcedureStepStartTime': '141000',
            'ScheduledStationAETitle': 'UNKNOWN',
            'ScheduledStationName': None,
            'SpecificCharacterSet': 'ISO_IR 100',
            'StudyInstanceUID': '1.3.6.1.4.1.31672.1.2.1.973852.91.1596520991.411',
            '_encoding': '8859/15',
            '_requestingPhysicianOBR': 'Docteur^Quenotte',
            '_requestingPhysicianORC': 'Docteur^Quenotte',
            '_scheduledProcedureStepStartDateTime': '20201001141000',
            '_sex': 'F'
        }

        builder.generate(values = values)

        wl_found = self.ob.modalities.find_worklist(
            modality="orthanc-a",
            query={
                'PatientID': "",
                "StudyInstanceUID": "",
                "AccessionNumber": ""
            }
        )

        self.assertEqual(1, len(wl_found))


    class MyDicomWorklistBuilder(DicomWorklistBuilder):

        def customize(self, ds: pydicom.dataset.FileDataset) -> pydicom.dataset.FileDataset:
            ds.StudyInstanceUID = ds.StudyInstanceUID[:60]
            return ds

    def test_customize(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            builder = TestDicomWorklistBuilder.MyDicomWorklistBuilder(folder=temporary_dir)
            values = {
                "AccessionNumber" : "1234",
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

            with dcmread(filename) as wl_readback:
                self.assertEqual(60, len(wl_readback.StudyInstanceUID))
                self.assertEqual("2", wl_readback.PatientID)
