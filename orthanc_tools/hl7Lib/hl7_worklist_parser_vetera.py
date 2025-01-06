from .hl7_worklist_parser import Hl7WorklistParser
import typing


class Hl7WorklistParserVetera(Hl7WorklistParser):

    def __init__(self, specific_fields: dict = None, patient_name_components_count: int = 5):

        vetera_dict = {
            'PatientID': 'PID.F2',
            'PatientSpeciesDescription': 'PID.F35',
            'PatientBreedDescription': 'PID.F36',
            'PatientSexNeutered': 'PID.F37',
            'BreedRegistrationNumber': 'PID.F38', # TO BE CONFIRMED (waiting for Vetera's feeback)
            '_scheduledProcedureStepStartDateTime': 'OBR.F6',
            'Modality': 'OBR.F21',
            'RequestingPhysician': 'OBR.F32'
        }
        if specific_fields is not None:
            vetera_dict.update(specific_fields)

        super(Hl7WorklistParserVetera, self).__init__(vetera_dict, patient_name_components_count)



    def parse(self, hl7_message: str) -> typing.Dict:
        # let's parse the default fields
        values = Hl7WorklistParser.parse(self, hl7_message=hl7_message)

        # let's parse according to rules specific to Vetera
        owner = self._get('PID.F5.R1.C1', default_value="")
        name = self._get('PID.F5.R1.C2', default_value="")

        # TODO confirm with the customer that this is what they want (because the owner name won't appear in Orthanc UI)
        values['ResponsiblePerson'] = owner
        values['PatientName'] = name

        if values.get('_scheduledProcedureStepStartDateTime') is not None:
            datetimeString = values.get('_scheduledProcedureStepStartDateTime')
            values['ScheduledProcedureStepStartDate'] = datetimeString[:8]  # date is made of the 8 first chars of the string
            if len(datetimeString) == 12:
                values['ScheduledProcedureStepStartTime'] = datetimeString[8:12] + "00"
            elif len(datetimeString) == 14:
                values['ScheduledProcedureStepStartTime'] = datetimeString[8:14]

        return values

