import unittest
import subprocess
import logging
from orthanc_api_client import OrthancApiClient
import orthanc_api_client.exceptions as api_exceptions
import pathlib
import os
from orthanc_tools import OrthancCloner
import hl7
import typing

here = pathlib.Path(__file__).parent.resolve()

def get_hl7_field(hl7_message, hl7_path):
    if len(hl7_path) == 1:
        return str(hl7_message[hlT_path[0]])
    else:
        return get_hl7_field(hl7_message[hl7_path[0]], hl7_path[1:])


class Hl7ToDicomMapper:


    def __init__(self, dicom_tags_from_hl7_mapping: typing.Dict[str, str]):
        self._dicom_tags_from_hl7_mapping = dicom_tags_from_hl7_mapping

    def _parse_hl7_message(self, message: str):
        hl7_message = hl7.parse(message)

        for dicom_tag, hl7_key in self._dicom_tags_from_hl7_mapping.items():
            hl7_path = hl7_key.split('.')
            # PID.F3 -> ['PID', 'F3']
            # PID.F3.R1.C1 -> ['PID', 'F3', 'R1', 'C1']

            hl7_path.insert(1, 0)
            # PID.F3 -> ['PID', 0, 'F3']
            # PID.F3.R1.C1 -> ['PID', 0, 'F3', 'R1', 'C1']


            if len(hl7_path) > 2 and hl7_path[2].startswith('F'):
                field_id = int(hl7_path[2].replace('F', ''))
                hl7_path[2] = field_id

                if len(hl7_path) > 3:  # ex: PID.F3.R1.C1 but not PID.F3
                    hl7_path.insert(3, 0)
                # PID.F3 -> ['PID', 0, 3]
                # PID.F3.R1.C1 -> ['PID', 0, 3, 0, 'R1', 'C1']

            
            if len(hl7_path) > 3 and hl7_path[3].startswith('R') and hl7_path[4].startswith('C'):
                r = int(hl7_path[2].replace('R', ''))
                c = int(hl7_path[3].replace('C', ''))
                hl7_path[2] = r

            value = get_hl7_field(hl7_message, hl7_path)
        toto = message
    
message = 'MSH|^~\&|GHH LAB|ELAB-3|GHH OE|BLDG4|200202150930||ORU^R01|CNTRL-3456|P|2.4\r'
message += 'PID|||555-44-4444||EVERYWOMAN^EVE^E^^^^L|JONES|196203520|F|||153 FERNWOOD DR.^^STATESVILLE^OH^35292||(206)3345232|(206)752-121||||AC555444444||67-A4335^OH^20030520\r'
message += 'OBR|1|845439^GHH OE|1045813^GHH LAB|1554-5^GLUCOSE|||200202150730||||||||555-55-5555^PRIMARY^PATRICIA P^^^^MD^^LEVEL SEVEN HEALTHCARE, INC.|||||||||F||||||444-44-4444^HIPPOCRATES^HOWARD H^^^^MD\r'
message += 'OBX|1|SN|1554-5^GLUCOSE^POST 12H CFST:MCNC:PT:SER/PLAS:QN||^182|mg/dl|70_105|H|||F\r'

mapping = {
            # --- PID segment
            'PatientID': 'PID.F3.R1.C1',
            'IssuerOfPatientID': 'PID.F3.R1.C4',
            'PatientName': 'PID.F5',  # IHE recommend to use the whole Field 5 as the patient name (it's usually full of ^ that is a separator in HL7 so we must take it as is without trying to parse it !
            'PatientMotherBirthName': 'PID.F6',
            'PatientBirthDate': 'PID.F7',
            '_sex': 'PID.F8',
            'PatientAddress' : 'PID.F11',

            # --- OBR segment
            'AccessionNumber': 'OBR.F18',
            'PatientState': 'OBR.F12',
            '_requestingPhysicianOBR': 'OBR.F16',
            'ReasonForTheRequestedProcedure': 'OBR.F31',
            'Modality': 'OBR.F24',
            'RequestedProcedureDescription': 'OBR.F4.R1.C2',
            #'ScheduledProcedureStepStartDateTime': 'OBR.F27.R1.C4',
            '_scheduledProcedureStepStartDateTime': 'OBR.F27.R1.C4',

            # --- PV1 segment
            '_ambulatoryStatus' : 'PV1.F15',
            'ReferringPhysicianName' : 'PV1.F8',
            'ConfidentialityConstraintOnPatientDataDescription' : 'PV1.F16',

            # --- ORC segment
            'OrderPlacerIdentifierSequence' : 'ORC.F2',
            'RequestedProcedureID' : 'ORC.F2',
            'ScheduledProcedureStepID' : 'ORC.F2',
            'OrderFillerIdentifierSequence' : 'ORC.F3',
            '_requestingPhysicianORC' : 'ORC.F12',

            # --- ZDS segment
            'StudyInstanceUID' : 'ZDS.F1.R1.C1'
        }

hl7message = hl7.parse(message)
print(hl7message)

mapper = Hl7ToDicomMapper(mapping)
mapper._parse_hl7_message(message)
