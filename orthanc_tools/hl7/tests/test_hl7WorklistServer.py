import unittest, os, glob
import hl7  # https://python-hl7.readthedocs.org/en/latest/
import pydicom
from hl7Lib import Hl7WorklistServer, MLLPClient, DicomWorklistBuilder, Hl7WorklistParser, Hl7MessageValidator
import tempfile
import time
import logging

class TestHl7WorklistServer(unittest.TestCase):

    def test_avignon_with_ge_modality(self):
        portNumber = 2000  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporaryDir:
            parser = Hl7WorklistParser()
            builder = DicomWorklistBuilder(folder = temporaryDir)

            with Hl7WorklistServer(
                    host = 'localhost',
                    port = portNumber,
                    parser = parser,
                    builder = builder,
                    logger = logging.getLogger('WORKLIST SERVER'),
                    automaticDeletionDelay = 2
            ) as server:
                # validate that ORM messages do create worklist files
                with MLLPClient('localhost', portNumber) as client:
                    hl7Request = hl7.parse(
                        "\x0bMSH|^~\&|myhospital.org|myhospital.org|||2017-04-25 07:31:13.123456||ORM^O01|269539|P|2.3.1|||||||||\r"
                        "PID|||1234567^^^myhospital.org||VANILL\xc9^LAURA^^^Mme^^L|MAIDEN^^^^^^L|19521103|F|||RUE MARIE CURIE^BRUXELLES^^74850^99100..LONG ADDRESS..1234567890123456789012345678901234567890|||||D|||272110608803615||||||||||20150930000000|Y|\r"
                        "PV1||N||||||REF^DOCTOR^JULIEN|||||||||\r"
                        "ORC|NW|723085|269539||SC|||||||CHUFJEA^CHIFREZE^JEAN FRANCOIS||\r"
                        "OBR||269539|269539|SC3TER.INJ^SCANNER \xc9 DE 3 TERRITOIRES ANATOMIQUES OU PLUS AVEC INJECTION \xe9||||||||||||||269539|269539||^^^^SCAN|||CT|||^^^201709141537^^R|||||||^^^^SCAN|\r"
                        "OBX||ST|^BODY WEIGHT||62|kg|||||F\r"
                        "OBX||ST|^BODY HEIGHT||1.90|m|||||F\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7Request)
                    hl7Response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporaryDir))
                self.assertEqual(1, len(files))
                worklistFilePath = files[0]

                # check the content of the file
                wl = pydicom.read_file(worklistFilePath)
                self.assertEqual("VANILLÉ^LAURA^^^Mme", wl.PatientName)
                self.assertEqual("19521103", wl.PatientBirthDate)
                self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)  # default char set if not specified in HL7 message
                self.assertEqual("SCANNER É DE 3 TERRITOIRES ANATOMIQUES OU PLUS AVEC INJECTION é", wl.RequestedProcedureDescription)
                self.assertEqual("CHUFJEA^CHIFREZE^JEAN FRANCOIS", wl.RequestingPhysician)
                self.assertEqual("MAIDEN", wl.PatientMotherBirthName.family_name)

                self.assertEqual("CT", wl.ScheduledProcedureStepSequence[0].Modality)
                self.assertEqual("20170914", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate)
                # make sure all 'mandatory' fields are there
                self.assertEqual("723085", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepID)
                self.assertEqual("UNKNOWN", wl.ScheduledProcedureStepSequence[0].ScheduledStationAETitle)
                self.assertEqual("REF^DOCTOR^JULIEN", wl.ReferringPhysicianName)
                self.assertEqual(0, len(wl.ReferencedStudySequence))
                self.assertEqual(0, len(wl.ReferencedPatientSequence))
                self.assertEqual("723085", wl.RequestedProcedureID)
                self.assertEqual("RUE MARIE CURIE^BRUXELLES^^74850^99100..LONG ADDRESS..123456...", wl.PatientAddress)

                # make sure the file has been deleted after the automaticDeletionDelay
                time.sleep(2.5)
                files = glob.glob('{path}/*.wl'.format(path = temporaryDir))
                self.assertEqual(0, len(files))

    def test_from_q_doc_chu_liege(self):
        portNumber = 2001  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporaryDir:
            parser = Hl7WorklistParser()
            builder = DicomWorklistBuilder(folder = temporaryDir)

            with Hl7WorklistServer(
                    host = 'localhost',
                    port = portNumber,
                    parser = parser,
                    builder = builder,
                    logger = logging.getLogger('WORKILIST SERVER'),
                    encoding = 'iso-8859-1'
            ) as server:
                # validate that ORM messages do create worklist files
                with MLLPClient('localhost', portNumber) as client:
                    sourceBinaryMessage = (b"\x0bMSH|^~\&|QDOC|HL7V1.1|AGFA|AGFA|20170505112549||ORM^O01|03139638|P|2.3.1||||||8859/1\r"
                                           b"PID|||123456Q||DUBOIS^Jean||19201231|M|||RUE DE LA STATION 14^^VILLAGE^^4999^BE||||||||12345678901\r"
                                           b"ORC|SC||N4568254^NDB||IP||^^^20170505111800^^R|||C123456||123456^DOCTEUR^NICOLA|||||^^L\r"
                                           b"OBR|||N4568254^NDB|CTCRANE^CT c\xe9r\xe9bral^QDOC^^^QUADRAT||20170505111800|20170505111800||||||||^^^NEURO CERV|123456^DOCTEUR^NICOLA||0897456|0897456|0897456|||||||^^^20170505111800^^R|||||||^^^NDB^CT NDB||20170505111800\r"
                                           b"ZDS|1.2.41.0.1.1.202.123.42.21.5832143.5832122^Agfa^Application^DICOM\r"
                                           b"\x1c\x0d")

                    response = client.send(sourceBinaryMessage)

                # make sure a file has been created
                worklistFilePath = os.path.join(temporaryDir, '0897456.wl')
                self.assertTrue(os.path.isfile(worklistFilePath))

                # check the content of the file
                wl = pydicom.read_file(worklistFilePath)
                self.assertEqual("DUBOIS^Jean", wl.PatientName)
                self.assertEqual("19201231", wl.PatientBirthDate)
                self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)
                self.assertEqual("CT cérébral", wl.RequestedProcedureDescription)

    def test_orthanc_worklist_c_find_encoding_bug(self):
        portNumber = 2002  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporaryDir:
            parser = Hl7WorklistParser()
            builder = DicomWorklistBuilder(folder = temporaryDir)

            with Hl7WorklistServer(
                    host = 'localhost',
                    port = portNumber,
                    parser = parser,
                    builder = builder,
                    logger = logging.getLogger('WORKILIST SERVER')
            ) as server:
                # validate that ORM messages do create worklist files
                with MLLPClient('localhost', portNumber) as client:
                    hl7Request = hl7.parse(
                        "\x0bMSH|^~\&|myhospital.org|myhospital.org|||2017-06-08 07:31:13.123456||ORM^O01|123456|P|2.3.1|||||||||\r"
                        "PID|||201102956^^^myhospital.org||VANILL\xc9^LAURA^^^Mme^^L|MAIDEN^^^^^^L|19521103|F|||RUE MARIE CURIE^BRUXELLES^^74850^99100|||||D|||272110608803615||||||||||20150930000000|Y|\r"
                        "PV1||N|||||||||||||||\r"
                        "ORC|NW|723085|123456||SC|||||||DOCTOR_CODE^DOCTOR^NAME||\r"
                        "OBR||123456|123456|STUDY_CODE^\xc9CHOGRAPHIE||||||||||||||123456|123456||^^^^SCAN|||CT|||^^^201706081537^^R|||||||^^^^SCAN|\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7Request)
                    hl7Response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporaryDir))
                self.assertEqual(1, len(files))
                worklistFilePath = files[0]

                # check the content of the file
                wl = pydicom.read_file(worklistFilePath)
                self.assertEqual("VANILLÉ^LAURA^^^Mme", wl.PatientName)
                self.assertEqual("MAIDEN^^^^^^L", wl.PatientMotherBirthName)
                self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)  # default char set if not specified in HL7 message
                self.assertEqual("ÉCHOGRAPHIE", wl.RequestedProcedureDescription)
                self.assertEqual("DOCTOR_CODE^DOCTOR^NAME", wl.RequestingPhysician)
                self.assertEqual("CT", wl.ScheduledProcedureStepSequence[0].Modality)
                self.assertEqual("20170608", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate)
