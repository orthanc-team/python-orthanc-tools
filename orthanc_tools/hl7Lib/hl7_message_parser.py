import typing
# from hl7Lib import Hl7MessageValidator
# from .hl7MessageValidator import Hl7MessageValidator
import hl7

class Hl7MessageParser:
    """
    Parses hl7Messages and stores the extracted values in a dictionary

    By default, this parser does not extract any field, you must tell him what he needs to find and where it needs to find them.
    parser = Hl7MessageParser()
    parser.set_field_definition('PatientID', 'PID.F3.R1.C1')


    """

    def __init__(self):
        self._hl7_message = None

        self.fields_definitions = {
            '_encoding': 'MSH.F18'
        }

    def set_field_definition(self, field_name: str, key: str):
        """
        :param fieldName: the name of the field to extract.  You should use the Dicom Tag name (i.e.: 'AccessionNumber')
        :param key: the HL7 location of the field to extract (i.e: 'OBR.F18' or 'PID.F3.R1.C4')
        :return:
        """
        self.fields_definitions[field_name] = key

    def add_fields_definitions(self, definitions: typing.Dict[str, str]):
        """
        :param definitions: a dictionary like: {'PatientID': 'PID.F3.R1.C1'}
        """
        for key, value in definitions.items():
            self.fields_definitions[key] = value

    def parse(self, message: str, strict: bool = True) -> typing.Dict[str, str]:
        # message = Hl7MessageValidator().validate(message, strict)
        self._hl7_message = hl7.parse(message)

        values = {}

        for field_name, key in self.fields_definitions.items():
            value = self._extract_field(key)
            if value is not None:
                values[field_name] = value

        return values

    def _extract_field(self,
                      key: str,
                      segment_index: int = 0,
                      default_value: str = None
                      ) -> str:
        keys = key.split('.')
        if len(keys) == 2:
            return self._get_whole_field(key, segment_index, default_value = default_value)
        elif len(keys) == 4:
            assert (segment_index == 0)  # _get does not support segmentIndex yet
            return self._get(key, default_value = default_value)


    def _get(self, key: str, default_value: str = None) -> str:
        try:
            return self._hl7_message[key]
        except KeyError:
            return None
        except IndexError:
            return default_value

    def _get_whole_field(self, key: str, segment_index: int = 0, default_value: str = None):
        try:
            # key is something like 'OBR.F16'
            keys = key.split('.')
            assert (len(keys) == 2)
            assert (keys[1][0] == 'F')

            value = str(self._hl7_message[keys[0]][segment_index][int(keys[1][1:])])
            if value == '':
                return None
            return value
        except KeyError:
            return None
        except IndexError:
            return default_value
