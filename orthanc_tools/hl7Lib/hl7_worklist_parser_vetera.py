from .hl7_worklist_parser import Hl7WorklistParser
import typing


class Hl7WorklistParserVetera(Hl7WorklistParser):

    def __init__(self, specific_fields: dict = None, patient_name_components_count: int = 5):

        vetera_dict = {
            'PatientID': 'PID.F2',
            'PatientSpeciesDescription': 'PID.F35',
            'PatientBreedDescription': 'PID.F36',
            'PatientSexNeutered': 'PID.F37',
            'BreedRegistrationNumber': 'PID.F38',
            '_scheduledProcedureStepStartDateTime': 'OBR.F6',
            'Modality': 'OBR.F21',
            'RequestingPhysician': 'OBR.F32',
            'RequestedProcedureDescription': 'OBR.F4'
        }
        if specific_fields is not None:
            vetera_dict.update(specific_fields)

        super(Hl7WorklistParserVetera, self).__init__(vetera_dict, patient_name_components_count)
