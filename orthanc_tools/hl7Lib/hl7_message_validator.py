import typing
import re

class Hl7MessageValidator:
    """
    This class validates the structure of HL7 message (it actually only checks the start/end chars and line splits)
    and returns a string with the real message.
    """

    def __init__(self, encoding: str = 'iso-8859-1', sb: bytes = b'\x0b', eb: bytes = b'\x1c', cr: bytes = b'\r'):
        self.encoding = encoding
        self.sb = sb
        self.eb = eb
        self.cr = cr
        self.validator = re.compile(self.sb.decode() + "(([^\r]+\r)*([^\r]+\r?))" + self.eb.decode() + self.cr.decode())
        self.validator_without_delimiters = re.compile("(([^\r]+\r)*([^\r]+\r?))")

    def validate(self, source: typing.Union[str, bytes], strict: bool = True) -> typing.Optional[str]:
        """
        validates the structure of HL7 message (mainly the delimiters) and returns a string with the real message in which the delimiters have been removed (the segment separator in the returned string is \r)
        :param source: a bytes array or str with the message
        :param strict: if False, it's not mandatory that the delimiters are present (i.e., whne reading the HL7 message from a file)
        :return:
        """
        if isinstance(source, str):
            bytes_message = source.encode()
        else:
            bytes_message = source

        # replace the \r\n by \r
        bytes_message = bytes_message.replace(b'\n', b'\r')
        bytes_message = bytes_message.replace(b'\r\r', b'\r')

        # first try to match the message including the delimiters
        matched = self.validator.match(bytes_message.decode(self.encoding))
        if matched is not None:
            return matched.groups()[0]

        if not strict:
            # then try to match the message without the delimiters (i.e if it comes from a file, it will not contain them)
            matched = self.validator_without_delimiters.match(bytes_message.decode(self.encoding))
            if matched is not None:
                return matched.groups()[0]

        return None
