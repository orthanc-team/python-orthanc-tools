from .hl7_worklist_parser import Hl7WorklistParser
import typing


class Hl7WorklistParserAssistovet(Hl7WorklistParser):

    def __init__(self, specific_fields: dict = None, patient_name_components_count: int = 5):
        super(Hl7WorklistParserAssistovet, self).__init__(specific_fields, patient_name_components_count)

    def parse(self, hl7_message: str) -> typing.Dict:
        # let's parse the default fields
        values = Hl7WorklistParser.parse(self, hl7_message=hl7_message)

        # let's add the field specific to Assistovet
        if values.get('PatientSpeciesDescription') is not None and values.get('PatientBreedDescription') is not None:
            # this should be an animal, so let's fill the responsible name
            last_name = self._get('PID.F5.R1.C1', default_value="")
            first_name = values.get('PatientMotherBirthName')
            if first_name is None: first_name = ""
            values['ResponsiblePerson'] = '^'.join([last_name, first_name])
        return values
