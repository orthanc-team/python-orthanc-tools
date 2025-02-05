import unittest
from orthanc_tools import Hl7WorklistParser


class TestHl7MessageExtractor(unittest.TestCase):
    message1 = (
        "\x0bMSH|^~\&|myhospital.org|myhospital.org|||2017-04-25 07:31:13.123456||ORM^O01|269539|P|2.3.1|||||||||\r"
        "PID|||201102956^^^myhospital.org||VANILLA^LAURA^^^Mme^^L|MAIDEN^^^^^^L|19521103|F|||RUE MARIE CURIE^BRUXELLES^^74850^99100|||||D|||272110608803615||||||||||20150930000000|Y|\r"
        "PV1||N|||||||||||||||\r"
        "ORC|NW|723085|269539||SC|||||||CHUFJEA^CHIFREZE^JEAN FRANCOIS||\r"
        "OBR||269539|269539|SC3TER.INJ^SCANNER DE 3 TERRITOIRES ANATOMIQUES OU PLUS AVEC INJECTION||||||||||||||269539|269539||^^^^SCAN|||CT|||^^^201408111537^^R|||||||^^^^SCAN|\r"
        "OBX||ST|^BODY WEIGHT||62|kg|||||F\r"
        "OBX||ST|^BODY HEIGHT||1.90|m|||||F\r"
        "\x1c\x0d"
    )

    def test_message_from_avignon(self):
        worklist_parser = Hl7WorklistParser()
        values = worklist_parser.parse(self.message1)

        self.assertEqual('F', values.get('PatientSex'))
        self.assertEqual('19521103', values.get('PatientBirthDate'))
        self.assertEqual('201102956', values.get('PatientID'))
        self.assertEqual('VANILLA^LAURA^^^Mme', values.get('PatientName'))
        self.assertEqual('myhospital.org', values.get('IssuerOfPatientID'))
        self.assertEqual('723085', values.get('OrderPlacerIdentifierSequence'))
        self.assertEqual('269539', values.get('OrderFillerIdentifierSequence'))
        self.assertEqual('269539', values.get('AccessionNumber'))
        self.assertEqual('CT', values.get('Modality'))
        self.assertEqual('SCANNER DE 3 TERRITOIRES ANATOMIQUES OU PLUS AVEC INJECTION', values.get('RequestedProcedureDescription'))
        self.assertEqual('20140811', values.get('ScheduledProcedureStepStartDate'))
        self.assertEqual('153700', values.get('ScheduledProcedureStepStartTime'))
        self.assertEqual('MAIDEN^^^^^^L', values.get('PatientMotherBirthName'))

    message_avignon_with_accent = (
        "\x0bMSH|^~\&|isc84.org|isc84.org|||2017-06-08 13:21:57.808791||ORM^O01|482124|P|2.3.1|||||||||\r"
        "PID|||201604549^^^isc84.org||TESTX^TESTY^^^Mme^^L|BOUCHER^^^^^^L|19730131|F|||28 AV DES PETUNIAS^DONZERE^^26290^991\r"
        "PV1||N|||||||||||||||\r"
        "ORC|NW|1001281|482124||SC|||||||DOYE^DOYER^MICHEL||\r"
        "OBR||482124|482124|ECAP^ÉCHOGRAPHIE DE L'ABDOMEN ET DU PETIT BASSIN (PELVIS)||||||||||||||482124|482124||^^^^ECHO||\r"
        "\x1c\x0d"
    )

    def test_message_from_avignon_with_accent(self):
        worklist_parser = Hl7WorklistParser()
        values = worklist_parser.parse(self.message_avignon_with_accent)

        self.assertEqual('ÉCHOGRAPHIE DE L\'ABDOMEN ET DU PETIT BASSIN (PELVIS)', values.get('RequestedProcedureDescription'))

    new_message_from_avignon = (
        "\x0bMSH|^~\&|Institut Ste Catherine|Institut Ste Catherine|||20250130152802||ORM^O01^ORM_O01|20250130152802966|P|2.5|||AL||FR||FR\r"
        "PID|||202303295^^^icap84.org^PI~139061305567914^^^ASIP-SANTE-INS-NIR&1.2.250.1.213.1.4.8&ISO^INS||TEST^LUCIEN^^^^^D~TEST^LUCIEN^^^^^L||19491230|M|||8 IMPASSE VIVALDI ^^VILLE^^84999||0780808008^PRN^PH~0123456789^PRN^CP~test.lucien@test.fr^NET^Internet||||||||||13055\r"
        "ORC|NW|999001714293|1714293||SC|||||||DOYE^DOYER^MICHEL\r"
        "OBR||1714293|1714293|DPAC^Depose de PAC^LOCAL|||20250130163000|20250130173000||||||||DOE^DOYER^MICHEL^^^DR^RAD||1714293||||||DX||||||||^^^SGT||||20250130163000\r"
        "\x1c\x0d"
    )
    def test_new_message_from_avignon(self):
        worklist_parser = Hl7WorklistParser()
        values = worklist_parser.parse(self.new_message_from_avignon)

        self.assertEqual('M', values.get('PatientSex'))
        self.assertEqual('19491230', values.get('PatientBirthDate'))
        self.assertEqual('202303295', values.get('PatientID'))
        self.assertEqual('TEST^LUCIEN^^^', values.get('PatientName'))
        self.assertEqual('icap84.org', values.get('IssuerOfPatientID'))
        self.assertEqual('999001714293', values.get('OrderPlacerIdentifierSequence'))
        self.assertEqual('1714293', values.get('OrderFillerIdentifierSequence'))
        self.assertEqual('1714293', values.get('AccessionNumber'))
        self.assertEqual('DX', values.get('Modality'))
        self.assertEqual('Depose de PAC', values.get('RequestedProcedureDescription'))
        self.assertEqual('20250130', values.get('ScheduledProcedureStepStartDate'))
        self.assertEqual('163000', values.get('ScheduledProcedureStepStartTime'))





    message2 = (
        "\x0bMSH|^~\&|MPA|SYSTEMA|IMPAX|MDRADAMB|200802210826||ORM^O01|MSG242081|P|2.3|\r"
        "PID|||0195313690^^^mpa||TEST^PATIENT|TEST|19500131|M|||Johann Reschstr.24^^Mannswoerth^^2320^AT||||||||2601||||||||Arb.|\r"
        "PV1||O|||||||||||||||||0855025211^^^^0855025211|000003||||||||||||||||||||||||20080220|\r"
        "ORC|NW|1552647.1|||||^^^20080221082647.1400^^3||20080220233830|MDIM-4A||A225021^Dietl^Christoph^^^OA Dr.|MDIM-4A_MDIM|\r"
        "OBR||1552647.1||ROE_CP^Cor pulmo^mpa^ROE_CP^CP^mpa||||||||||||A225021^Dietl^Christoph^^^OA Dr.|||1552647.1|1552647.1||||CR|||^^^^20080221^3|\r"
        "ZDS|1.2.4.0.13.1.432252867.1552647.1^100^Application^DICOM\r"
        "\x1c\x0d"
    )

    def test_message2(self):
        worklist_parser = Hl7WorklistParser()
        values = worklist_parser.parse(self.message2)

        self.assertEqual('19500131', values.get('PatientBirthDate'))
        self.assertEqual('0195313690', values.get('PatientID'))
        self.assertEqual('TEST^PATIENT', values.get('PatientName'))
        self.assertEqual('mpa', values.get('IssuerOfPatientID'))
        self.assertEqual('A225021^Dietl^Christoph^^^OA Dr.', values.get('RequestingPhysician'))
        self.assertEqual('1552647.1', values.get('OrderPlacerIdentifierSequence'))
        self.assertEqual('1.2.4.0.13.1.432252867.1552647.1', values.get('StudyInstanceUID'))
        self.assertEqual('CR', values.get('Modality'))
        self.assertEqual('Cor pulmo', values.get('RequestedProcedureDescription'))
        # self.assertEqual('20080221', values.get('ScheduledProcedureStepStartDateTime'))
        # self.assertEqual('1552647.1', values.get('AccessionNumber')) I actually don't know where the AccessionNumber is supposed to be in this message !!



        # Sample message from DicomGrid:
        # * The orders (ORM^O01) should contain the following information.
        # * MRN in PID2 or PID3
        # * Patient name in PID5
        # * Accession number in ORC3 or OBR3 or MHS10
        # * Birth date in PID7
        # * Sex in PID8
        # * Modality in OBR20
        # * Requested procedure id in OBR4-1 or ORC2
        # * Requested procedure description in OBR4-2
        # * Requested procedure step start date in OBR27-4
        # * Requested procedure station aetitle in OBR19
        #
        # Below is an example ORM^O01 message that is part of the modality worklist workflow

    message3 = (
        "\x0bMSH|^~\&|EMR|EMR|||20041111072701|1148|ORM^O01|497|D|2.3||\r"
        "PID|1||43560^^^^EPI||ECKLES^SAMUEL^A.^^MR.^||19730211|M||AfrAm|42 NORTH AVE^^CAMBRIDGE^MA^02138^US^^^DN|DN| DN|(857)721-3255-|(857)721-3255||S||11480003~2514705~7603~13412|114-82-1544||||^^^MA^^NTE|1||Comments go here\r"
        "PD1|||FRANKLIN NEAR EAST LOCATION (CENTRAL)^^537|757^SPETZLER^CHRISTIAN^J^^^\r"
        "PV1|||^^^EMR^^^^^||||||||||||||||509502||||||||||||||||||||||||||||||||VORC|NW|363463^EPC|1858^EPC||Final||^^^200308151200^^^^||200401220727|1152^KARIS^LUCAS^^^^||757^SPETZLER^CHRISTIAN^J^^^|467^^^537^^^^^|(857)259-9167||\r"
        "OBR|1|363463|1858^EPC|73610^X-RAY ANKLE 3+ VW^^^X-RAY ANKLE||||||||||||757^SPETZLER^CHRISTIAN^J^^^|(857)259-9167||||||||Final||^^^200308151200^^^^|||||2149^HITACHI^BENJAMIN^^^^||1148010^1A^FRANKLIN^XRAY^^^|^|\r"
        "DG1||I9|824^ANKLE FRACTURE^I9|ANKLE FRACTURE||\r"
        "\x1c\x0d"
    )

    def test_message3(self):
        worklist_parser = Hl7WorklistParser()
        worklist_parser.set_field_definition('AccessionNumber', 'OBR.F3')

        values = worklist_parser.parse(self.message3)

        self.assertEqual('19730211', values.get('PatientBirthDate'))
        self.assertEqual('43560', values.get('PatientID'))
        self.assertEqual('M', values.get('PatientSex'))
        self.assertEqual('ECKLES^SAMUEL^A.^^MR.', values.get('PatientName'))
        self.assertEqual(None, values.get('Modality'))
        self.assertEqual('757^SPETZLER^CHRISTIAN^J^^^', values.get('RequestingPhysician'))
        self.assertEqual('1858^EPC', values.get('AccessionNumber'))
        self.assertEqual('X-RAY ANKLE 3+ VW', values.get('RequestedProcedureDescription'))
        self.assertEqual('20030815', values.get('ScheduledProcedureStepStartDate'))
        self.assertEqual('120000', values.get('ScheduledProcedureStepStartTime'))
