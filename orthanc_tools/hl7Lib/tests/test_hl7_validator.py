import unittest
from orthanc_tools import Hl7MessageValidator


class TestHl7MessageValidator(unittest.TestCase):

    def test_short_hl7_valid_message(self):

        # small valid HL7 message: only the delimiters and a short line
        validator = Hl7MessageValidator()
        message = validator.validate(b'\x0bMSH\r\x1c\x0d')
        self.assertEqual('MSH\r', message)

        message = validator.validate(b'\x0bMSH\rPID\r\x1c\x0d')
        self.assertEqual('MSH\rPID\r', message)

    def test_short_hl7_valid_message_with_cr_lf(self):

        # small valid HL7 message: only the delimiters and a short line
        validator = Hl7MessageValidator()
        message = validator.validate(b'\x0bMSH\r\n\x1c\x0d')
        self.assertEqual('MSH\r', message)

        message = validator.validate(b'\x0bMSH\r\nPID\r\n\x1c\x0d')
        self.assertEqual('MSH\rPID\r', message)

    def test_short_hl7_valid_message_without_delimiters(self):

        # small valid HL7 message: only the delimiters and a short line
        validator = Hl7MessageValidator()
        message = validator.validate(b'MSH\r', strict = False)
        self.assertEqual('MSH\r', message)

        message = validator.validate(b'MSH\rPID\r', strict = False)
        self.assertEqual('MSH\rPID\r', message)

    def test_short_hl7_valid_message_with_cr_lf_without_delimiters(self):

        # small valid HL7 message: only the delimiters and a short line
        validator = Hl7MessageValidator()
        message = validator.validate(b'MSH\r\n', strict = False)
        self.assertEqual('MSH\r', message)

        message = validator.validate(b'MSH\r\nPID\r\n', strict = False)
        self.assertEqual('MSH\rPID\r', message)


    def test_short_hl7_invalid_messages(self):
        validator = Hl7MessageValidator()

        # test with a bunch of invalid messages
        message = validator.validate(b'\rMSH\r\x1c\x0d')
        self.assertIsNone(message)

        message = validator.validate(b'\rMSH\x1c\x0d')
        self.assertIsNone(message)

        message = validator.validate(b'x0bMSH\r\n\x0d')
        self.assertIsNone(message)

        message = validator.validate(b'\x0bMSH\r\n\x1c\x0c')
        self.assertIsNone(message)

    def test_normal_hl7_valid_message(self):

        # valid HL7 message
        validator = Hl7MessageValidator()
        message = validator.validate(b'\x0bMSH|^~\\&|CATH|StJohn|AcmeHIS|StJohn|20061019172719||ACK^O01|MSGID12349876|P|2.3\rMSA|AR|MSGID12349876|error\r\x1c\x0d')
        self.assertEqual(r'MSH|^~\&|CATH|StJohn|AcmeHIS|StJohn|20061019172719||ACK^O01|MSGID12349876|P|2.3' + '\rMSA|AR|MSGID12349876|error\r', message)
