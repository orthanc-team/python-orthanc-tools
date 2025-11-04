import unittest
from orthanc_tools import Hl7MessageParser


class TestHl7MessageParser(unittest.TestCase):

    def test_message(self):
        message = (
            "\x0bMSH|^~\\&|myhospital.org|myhospital.org|||2017-04-25 07:31:13.123456||ORM^O01|269539|P|2.3.1|||||||||\r"
            "\x1c\x0d"
        )
        parser = Hl7MessageParser()
        values = parser.parse(message)


