import contextlib
import typing
# from hl7Lib import Hl7MessageParser
from .hl7_message_parser import Hl7MessageParser


class Hl7ReportParser(Hl7MessageParser):

    def __init__(self, specific_fields: dict = None):
        super(Hl7ReportParser, self).__init__()

        # Let's add "standards" field
        self.add_fields_definitions({
            # --- PID segment
            'PatientID': 'PID.F3.R1.C1',
            'PatientName': 'PID.F5',  # IHE recommend to use the whole Field 5 as the patient name (it's usually full of ^ that is a separator in HL7 so we must take it as is without trying to parse it !
            'PatientBirthDate': 'PID.F7',

            # --- OBR segment
            'StudyInstanceUID': 'OBR.F3.R1.C1',

            # --- OBX Segment
            'Base64Report': 'OBX.F5.R1.C5'
        })

        # Let's add specific fields (they will override the default ones if any)
        if specific_fields is not None:
            self.add_fields_definitions(specific_fields)

    def parse(self, hl7_message: str) -> typing.Dict:

        # extract field the default way
        values = super(Hl7ReportParser, self).parse(hl7_message, strict = False)

        # keep only the first 5 components of the name according to http://dicom.nema.org/dicom/2013/output/chtml/part05/sect_6.2.html (check PN VR definition)
        values['PatientName'] = '^'.join(values['PatientName'].split('^')[:5])

        # clean birthdate
        values['PatientBirthDate'] = values['PatientBirthDate'][0:8]

        return values

