import unittest, os, glob
import hl7  # https://python-hl7.readthedocs.org/en/latest/
import pydicom
from pydicom import dcmread
from orthanc_tools import MLLPClient, DicomWorklistBuilder, Hl7WorklistParser, Hl7MessageValidator, MLLPServer, Hl7OrmWorklistMsgHandler, Hl7WorklistParserAssistovet, Hl7WorklistParserVetera
import tempfile
import logging
import typing


class TestHl7OrmWorklistMsgHandler(unittest.TestCase):

    def test_avignon_with_ge_modality(self):
        port_number = 2002  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporary_dir:
            parser = Hl7WorklistParser()
            builder = DicomWorklistBuilder(folder = temporary_dir)
            orm_handler = Hl7OrmWorklistMsgHandler(parser=parser, builder=builder)

            mllp_server = MLLPServer(
                    host = 'localhost',
                    port = port_number,
                    handlers = {
                        'ORM^O01': (orm_handler.handle_orm_message,)
                    }
            )

            mllp_server.add_handlers({'ORM^O01': (orm_handler.handle_orm_message,)})

            with mllp_server as server:
                # validate that ORM messages do create worklist files
                with MLLPClient('localhost', port_number) as client:
                    hl7_request = hl7.parse(
                        "\x0bMSH|^~\&|myhospital.org|myhospital.org|||2017-04-25 07:31:13.123456||ORM^O01|269539|P|2.3.1|||||||||\r"
                        "PID|||1234567^^^myhospital.org||VANILL\xc9^LAURA^^^Mme^^L|MAIDEN^^^^^^L|19521103|F|||RUE MARIE CURIE^BRUXELLES^^74850^99100..LONG ADDRESS..1234567890123456789012345678901234567890|||||D|||272110608803615||||||||||20150930000000|Y|\r"
                        "PV1||N||||||REF^DOCTOR^JULIEN|||||||||\r"
                        "ORC|NW|723085|269539||SC|||||||CHUFJEA^CHIFREZE^JEAN FRANCOIS||\r"
                        "OBR||269539|269539|SC3TER.INJ^SCANNER \xc9 DE 3 TERRITOIRES ANATOMIQUES OU PLUS AVEC INJECTION \xe9||||||||||||||269539|269539||^^^^SCAN|||CT|||^^^201709141537^^R|||||||^^^^SCAN|\r"
                        "OBX||ST|^BODY WEIGHT||62|kg|||||F\r"
                        "OBX||ST|^BODY HEIGHT||1.90|m|||||F\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7_request)
                    hl7_response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporary_dir))
                self.assertEqual(1, len(files))
                worklist_file_path = files[0]

                # check the content of the file
                with dcmread(worklist_file_path) as wl:
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

    def test_from_q_doc_chu_liege(self):
        port_number = 2003  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporary_dir:
            parser = Hl7WorklistParser({'AccessionNumber': 'OBR.F18'})
            builder = DicomWorklistBuilder(folder = temporary_dir)
            orm_handler = Hl7OrmWorklistMsgHandler(parser=parser, builder=builder)

            with MLLPServer(
                    host = 'localhost',
                    port = port_number,
                    handlers = {
                    'ORM^O01': (orm_handler.handle_orm_message,)
                    }
            ) as server:
                # validate that ORM messages do create worklist files
                with MLLPClient('localhost', port_number) as client:
                    source_binary_message = (b"\x0bMSH|^~\&|QDOC|HL7V1.1|AGFA|AGFA|20170505112549||ORM^O01|03139638|P|2.3.1||||||8859/1\r"
                                           b"PID|||123456Q||DUBOIS^Jean||19201231|M|||RUE DE LA STATION 14^^VILLAGE^^4999^BE||||||||12345678901\r"
                                           b"ORC|SC||N4568254^NDB||IP||^^^20170505111800^^R|||C123456||123456^DOCTEUR^NICOLA|||||^^L\r"
                                           b"OBR|||N4568254^NDB|CTCRANE^CT c\xe9r\xe9bral^QDOC^^^QUADRAT||20170505111800|20170505111800||||||||^^^NEURO CERV|123456^DOCTEUR^NICOLA||0897456|0897456|0897456|||||||^^^20170505111800^^R|||||||^^^NDB^CT NDB||20170505111800\r"
                                           b"ZDS|1.2.41.0.1.1.202.123.42.21.5832143.5832122^Agfa^Application^DICOM\r"
                                           b"\x1c\x0d")

                    response = client.send(source_binary_message)

                # make sure a file has been created
                worklist_file_path = os.path.join(temporary_dir, '0897456.wl')
                self.assertTrue(os.path.isfile(worklist_file_path))

                # check the content of the file
                with dcmread(worklist_file_path) as wl:
                    self.assertEqual("DUBOIS^Jean", wl.PatientName)
                    self.assertEqual("19201231", wl.PatientBirthDate)
                    self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)
                    self.assertEqual("CT cérébral", wl.RequestedProcedureDescription)

                    # check that the specific field is correctly handled
                    self.assertEqual("0897456", wl.AccessionNumber)

    def test_orthanc_worklist_c_find_encoding_bug(self):
        port_number = 2004  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporary_dir:
            parser = Hl7WorklistParser()
            builder = DicomWorklistBuilder(folder = temporary_dir)
            orm_handler = Hl7OrmWorklistMsgHandler(parser=parser, builder=builder)

            with MLLPServer(
                    host='localhost',
                    port=port_number,
                    handlers={
                        'ORM^O01': (orm_handler.handle_orm_message,)
                    }
            ) as server:
                # validate that ORM messages do create worklist files
                with MLLPClient('localhost', port_number) as client:
                    hl7_request = hl7.parse(
                        "\x0bMSH|^~\&|myhospital.org|myhospital.org|||2017-06-08 07:31:13.123456||ORM^O01|123456|P|2.3.1|||||||||\r"
                        "PID|||201102956^^^myhospital.org||VANILL\xc9^LAURA^^^Mme^^L|MAIDEN^^^^^^L|19521103|F|||RUE MARIE CURIE^BRUXELLES^^74850^99100|||||D|||272110608803615||||||||||20150930000000|Y|\r"
                        "PV1||N|||||||||||||||\r"
                        "ORC|NW|723085|123456||SC|||||||DOCTOR_CODE^DOCTOR^NAME||\r"
                        "OBR||123456|123456|STUDY_CODE^\xc9CHOGRAPHIE||||||||||||||123456|123456||^^^^SCAN|||CT|||^^^201706081537^^R|||||||^^^^SCAN|\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7_request)
                    hl7Response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporary_dir))
                self.assertEqual(1, len(files))
                worklist_file_path = files[0]

                # check the content of the file
                with dcmread(worklist_file_path) as wl:
                    self.assertEqual("VANILLÉ^LAURA^^^Mme", wl.PatientName)
                    self.assertEqual("MAIDEN^^^^^^L", wl.PatientMotherBirthName)
                    self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)  # default char set if not specified in HL7 message
                    self.assertEqual("ÉCHOGRAPHIE", wl.RequestedProcedureDescription)
                    self.assertEqual("DOCTOR_CODE^DOCTOR^NAME", wl.RequestingPhysician)
                    self.assertEqual("CT", wl.ScheduledProcedureStepSequence[0].Modality)
                    self.assertEqual("20170608", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate)

    def test_ried_worklists(self):
        port_number = 2005  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporary_dir:
            parser = Hl7WorklistParser()
            builder = DicomWorklistBuilder(folder = temporary_dir)
            orm_handler = Hl7OrmWorklistMsgHandler(parser=parser, builder=builder)

            mllp_server = MLLPServer(
                    host = 'localhost',
                    port = port_number,
                    handlers = {
                    'ORM^O01^ORM_O01': (orm_handler.handle_orm_message,)
                    }
            )

            with mllp_server as server:
                # validate that ORM messages do create worklist files
                with MLLPClient('localhost', port_number) as client:
                    hl7_request = hl7.parse(
                        "\x0bMSH|^~\&|ECSIMAGING|CORADIX|BEA|BEA|20201001140735||ORM^O01^ORM_O01|6af22cb1-38af-4dc7-93d5-83e749394237|P|2.3.1|||||FRA|8859/15|FRA||\r"
                        "PID|1||5343197^^^ECSIMAGING^PI||LLOxxx^Simxxx^^^^^D~LLOxxx^Simxxx^^^^^L||19550812000000|F|||2 rue ^^THUIR^^66300^^H||^^PH^^^^^^^^^0404040404~^^CP^^^^^^^^^0606060606|||U||A1.02412251^^^ECSIMAGING^AN||||||||^^||^^||\r"
                        "PV1||O||R||||Docteur^Traitant|||||||||||A1.02412251^^^ECSIMAGING^VN|||||||||||||||||||||||||20201001134400||||||||\r"
                        "ORC|NW|3264557^ECSIMAGING|3264557^ECSIMAGING|2412251^ECSIMAGING|||1^^^20201001141000|||||Docteur^Quenotte|||20201001141000||||||||||\r"
                        "OBR|1||3264557^ECSIMAGING|I90 FOIE IV^IRM FOIE IV^ECSIMAGING^ZCQJ004^IRM FOIE IV^CCAM||||||||||||Docteur^Quenotte||||||||NMR|||1^^20^20201001141000\r"
                        "ZDS|1.3.6.1.4.1.31672.1.2.1.973852.91.1596520991.411\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7_request)
                    hl7Response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporary_dir))
                self.assertEqual(1, len(files))
                worklist_file_path = files[0]

                # check the content of the file
                with dcmread(worklist_file_path) as wl:
                    self.assertEqual("LLOxxx^Simxxx^^^", wl.PatientName)
                    self.assertEqual("19550812", wl.PatientBirthDate)
                    self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)  # default char set if not specified in HL7 message
                    self.assertEqual("IRM FOIE IV", wl.RequestedProcedureDescription)
                    self.assertEqual("Docteur^Quenotte", wl.RequestingPhysician)
                    self.assertEqual("NMR", wl.ScheduledProcedureStepSequence[0].Modality)
                    self.assertEqual("20201001", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate)

                    # make sure all 'mandatory' fields are there
                    self.assertEqual("3264557", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepID)
                    self.assertEqual("UNKNOWN", wl.ScheduledProcedureStepSequence[0].ScheduledStationAETitle)
                    self.assertEqual("Docteur^Traitant", wl.ReferringPhysicianName)
                    self.assertEqual("3264557", wl.RequestedProcedureID)
                    self.assertEqual("2 rue ^^THUIR^^66300^^H", wl.PatientAddress)
                    self.assertEqual("3264557", wl.AccessionNumber)


    def test_isosl_worklists(self):
        port_number = 2006  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)
        with tempfile.TemporaryDirectory() as temporary_dir:

            # specific field for isosl
            extra_fields = {
                # --- PID segment
                'OtherPatientIDs': 'PID.F4.R1.C1',
                'AccessionNumber': 'PV1.F19.R1.C1',
                'ReferringPhysicianName': 'PV1.F7',
                'RequestingPhysician': 'PV1.F9'
            }

            parser = Hl7WorklistParser(extra_fields, patient_name_components_count=4)
            builder = DicomWorklistBuilder(folder = temporary_dir)
            orm_handler = Hl7OrmWorklistMsgHandler(parser=parser, builder=builder)

            mllp_server = MLLPServer(
                    host='localhost',
                    port=port_number,
                    handlers={
                    'ADT^A04': (orm_handler.handle_orm_message,)
                    }
            )

            with mllp_server as server:
                # validate that ADT messages do create worklist files
                with MLLPClient('localhost', port_number) as client:
                    hl7_request = hl7.parse(
                        "\x0bMSH|^~\&|OAZIS||||20230404090644||ADT^A04|01370309|P|2.3||||||8859/1\r"
                        "EVN|A04|20230404090644|||AGIRMANSPOL|202304040906\r"
                        "PID|1||341410|91041739368^^^^NN|Moraloa^Salva Bernard^^^Monsieur||19910417|U|||Rue No\xe9 11^^VISE^^4200^BE^H||0499/244732^^CP||FR|U||20624682|0000000000|91041739368||||||BE||||N\r"
                        "PD1||||16409914^GILON^PIERRE||||||||N\r"
                        "NK1|1|BALLROS MARIA|OTH^Autre|. ^^^^null|||CP^1|19900101\r"
                        "NK1|2|BALLROS MARIA|OTH^Autre|AV.G.TRUFFEE,21/009 ^^LIEGE^^4020^BE|||CP^2|19900101\r"
                        "NK1|3|BALLROS MARIA|OTH^Autre|AV.G.TRUFFEE,21/009 ^^LIEGE^^4020^BE|||CP^3|19900101\r"
                        "NK1|4|BALLROS MARIA|F_A^Adresse de facturation|av.G.TRUFFEE,17/009 ^^LIEGE^^4020^BE|||BP^4|19000101\r"
                        "PV1|1|O|POLY^001^048^310^0^2^^POLY|POLY31|||16409914^GILSON^MARC||16371009^THISO^DANILO|1950|||||||16371009^THISO^DANILO|0|23016738^^^^VN|1^20230404|||||||||||||||||||O|||||202304040906\r"
                        "PV2|||NULL||||||202304042106|0|||||||||||0|N||||||||T||||||||0///09/\r"
                        "IN1|1|1|319000|Mutualit\xe9 Solidaris Wallonie|Rue des Dominicaines 35 ^^SAINT-SERVAIS^^5002^BE||078/05 13 19|||||20110401|||||0|| ||||||||||||||||||||||||||||111/111||91041739368\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7_request)
                    hl7Response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporary_dir))
                self.assertEqual(1, len(files))
                worklist_file_path = files[0]

                # check the content of the file
                with dcmread(worklist_file_path) as wl:
                    self.assertEqual("Moraloa^Salva Bernard^^", wl.PatientName)
                    self.assertEqual("19910417", wl.PatientBirthDate)
                    # TODO: check the characterSet with the customer !
                    self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)  # default char set if not specified in HL7 message
                    self.assertEqual("16371009^THISO^DANILO", wl.RequestingPhysician)

                    # make sure all 'mandatory' fields are there
                    self.assertEqual("UNKNOWN", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepID)
                    self.assertEqual("UNKNOWN", wl.ScheduledProcedureStepSequence[0].ScheduledStationAETitle)
                    self.assertEqual("16409914^GILSON^MARC", wl.ReferringPhysicianName)
                    self.assertEqual("UNKNOWN", wl.RequestedProcedureID)
                    self.assertEqual("Rue Noé 11^^VISE^^4200^BE^H", wl.PatientAddress)
                    self.assertEqual("23016738", wl.AccessionNumber)
                    self.assertEqual("", wl.PatientSex)

    def test_assistovet_worklists(self):
        port_number = 2007  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)

        with tempfile.TemporaryDirectory() as temporary_dir:

            parser = Hl7WorklistParserAssistovet()
            builder = DicomWorklistBuilder(folder = temporary_dir)
            orm_handler = Hl7OrmWorklistMsgHandler(parser=parser, builder=builder)

            mllp_server = MLLPServer(
                    host='localhost',
                    port=port_number,
                    handlers={
                    'ORM^O01': (orm_handler.handle_orm_message,)
                    }
            )

            with mllp_server as server:
                # validate that ADT messages do create worklist files
                with MLLPClient('localhost', port_number) as client:
                    hl7_request = hl7.parse(
                        "\x0bMSH|^~\&|AssistoVetMaestro|AssistoVetSystems|Echographie|Philips|20231109114936||ORM^O01|20231109114936-111717488|P|2.3.1|\r"
                        "PID|||3951-1^^^MYPACS|250268731025243^|BENARD^HORUS|Maverick|20120824|M|Chien|Berger belge malinois|20 Rue des Moulins - 45430 MARDIE||||||||||||||||ALTERED\r"
                        "PV1||O||||||M^Alfred Canard^rue des Sorbiers - 4800 Verviers|||||||||||||||||||||||\r"
                        "ORC|NW|181416|181416||SC||^^^20231109114936||||||||||\r"
                        "OBR|1|181416|181416|DX1^RADIO||||||||||||||20231109114936|ECHO2|20231109114936-111717488||||US\r"
                        "OBX|1|ST|1010.1^BODY WEIGHT||36.000|kg|||||F\r"
                        "ZDS|1.2.4.0.13.1.4.2252867.20231109114936|MYLAB||||\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7_request)
                    hl7Response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporary_dir))
                self.assertEqual(1, len(files))
                worklist_file_path = files[0]

                # check the content of the file
                with dcmread(worklist_file_path) as wl:
                    self.assertEqual("BENARD^HORUS", wl.PatientName)
                    self.assertEqual("20120824", wl.PatientBirthDate)
                    self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)  # default char set if not specified in HL7 message

                    # make sure all 'mandatory' fields are there
                    self.assertEqual("181416", wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepID)
                    self.assertEqual("UNKNOWN", wl.ScheduledProcedureStepSequence[0].ScheduledStationAETitle)
                    self.assertEqual("M^Alfred Canard^rue des Sorbiers - 4800 Verviers", wl.ReferringPhysicianName)
                    self.assertEqual("181416", wl.RequestedProcedureID)
                    self.assertEqual("20 Rue des Moulins - 45430 MARDIE", wl.PatientAddress)
                    self.assertEqual("181416", wl.AccessionNumber)
                    self.assertEqual(36.000, wl.PatientWeight)
                    self.assertEqual("Chien", wl.PatientSpeciesDescription)
                    self.assertEqual("Berger belge malinois", wl.PatientBreedDescription)
                    self.assertEqual("250268731025243", wl.OtherPatientIDs)
                    self.assertEqual("M", wl.PatientSex)
                    self.assertEqual("BENARD^Maverick", wl.ResponsiblePerson)
                    self.assertEqual("ALTERED", wl.PatientSexNeutered)
                    self.assertEqual("20231109",  wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate)
                    self.assertEqual("114936",  wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartTime)


    def test_vetera_worklists(self):
        port_number = 2008  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)

        with tempfile.TemporaryDirectory() as temporary_dir:

            parser = Hl7WorklistParserVetera()
            builder = DicomWorklistBuilder(folder = temporary_dir)
            orm_handler = Hl7OrmWorklistMsgHandler(parser=parser, builder=builder)

            mllp_server = MLLPServer(
                    host='localhost',
                    port=port_number,
                    handlers={
                    'ORM^O01': (orm_handler.handle_orm_message,)
                    }
            )

            with mllp_server as server:
                # validate that ADT messages do create worklist files
                with MLLPClient('localhost', port_number) as client:
                    hl7_request = hl7.parse(
                        "\x0bMSH|^~\&|VETERA|VETERA|conquest|conquest|20170731081517||ORM^O01|1000000001|P|2.5.0|||||\r"
                        "PID|1|999888777||123456789012345|GP.Software^Vetera||20070501|F|||||||||||||||||||||||||||Katze|Balinese|ALTERED|ZH-123|\r"
                        "ORC|NW||||||||20170731081517||||||||||\r"
                        "OBR|||1000000001|HD||20170731081517|||||||||||||||DX|||ZUG||||||||Dr. P. Muster||||\r"
                        "\x1c\x0d"
                    )
                    response = client.send(hl7_request)
                    hl7Response = hl7.parse(response)

                # make sure a file has been created
                files = glob.glob('{path}/*.wl'.format(path = temporary_dir))
                self.assertEqual(1, len(files))
                worklist_file_path = files[0]

                #TODO:
                # check the content of the file
                with dcmread(worklist_file_path) as wl:
                    self.assertEqual("GP.Software^Vetera", wl.PatientName)
                    self.assertEqual("20070501", wl.PatientBirthDate)
                    self.assertEqual("999888777", wl.PatientID)
                    self.assertEqual("ISO_IR 100", wl.SpecificCharacterSet)  # default char set if not specified in HL7 message

                    # make sure all 'mandatory' fields are there
                    self.assertEqual("123456789012345", wl.OtherPatientIDs)
                    self.assertEqual("Katze", wl.PatientSpeciesDescription)
                    self.assertEqual("Balinese", wl.PatientBreedDescription)
                    self.assertEqual("ALTERED", wl.PatientSexNeutered)
                    self.assertEqual("ZH-123", wl.BreedRegistrationNumber)
                    self.assertEqual("20170731",  wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate)
                    self.assertEqual("081517",  wl.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartTime)
                    self.assertEqual("1000000001", wl.AccessionNumber)
                    self.assertEqual("F", wl.PatientSex)
                    self.assertEqual("DX", wl.ScheduledProcedureStepSequence[0].Modality)
                    self.assertEqual("Dr. P. Muster", wl.RequestingPhysician)

