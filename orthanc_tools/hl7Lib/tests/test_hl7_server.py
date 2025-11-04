import unittest
import hl7  # https://python-hl7.readthedocs.org/en/latest/
#import hl7Lib
from orthanc_tools import hl7Lib
import socket
from time import strftime
import time
import re
from orthanc_tools import MLLPServer, MLLPClient


def hl7_echo_message_handler(incoming_hl7_message: str) -> hl7.Message:
    """
    This is a 'stupid' handler that just repeats the message it receives (useful for testing)
    """
    return hl7.parse(incoming_hl7_message)


def hl7_default_error_handler(incoming_hl7_message: str, error_description: str) -> hl7.Message:
    """
    This is a 'stupid' handler that just returns a simple error message
    """
    hl7_response = hl7.parse(
            "MSH|^~\&|CATH|StJohn|AcmeHIS|StJohn|20061019172719||ACK^O01|MSGID12349876|P|2.3\rMSA|AR|MSGID12349876|{error}".format(error = error_description))
    return hl7_response


class TestHl7Server(unittest.TestCase):

    def test_start_and_stop(self):
        server = MLLPServer('localhost', 2575, {
        })

        # just make sure we can start/stop the server
        self.assertFalse(server.is_running())

        server.start()
        self.assertTrue(server.is_running())

        server.stop()
        self.assertFalse(server.is_running())

    def test_start_and_stop_in_scope(self):
        # just make sure we can start/stop the server in a scoped statement
        with MLLPServer('localhost', 2575, {}) as server:
            self.assertTrue(server.is_running())

        # out of the 'with' statement, it should be stopped
        self.assertFalse(server.is_running())

    def test_echo(self):
        port_number = 2102  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)

        # start a server that will echo all ORU^R01 messages and return an error message for all other message types
        with MLLPServer('localhost', port_number, {
            'ORU^R01': (hl7_echo_message_handler,),
            'ERR': (hl7_default_error_handler,)
        }) as server:
            # validate that ORU^R01 messages are echoed
            with MLLPClient('localhost', port_number) as client:
                hl7_oru_r01_request = hl7.parse(
                    "MSH|^~\&|TOTO|TUTU|SOFTNAME|CHABC|201602011049||ORU^R01|exp_ANE_5|P|2.3.1\rPID|1||8123456DK01||DUPONT^ALBERT ANTHONY|||||||||||||123456")
                response = client.send(hl7_oru_r01_request)
                hl7_response = hl7.parse(response)

                self.assertEqual(hl7_oru_r01_request, hl7_response)

            # validate that other messages returns an negative acknowledge (error generated in the server)
            with MLLPClient('localhost', port_number) as client:
                hl7_other_request = hl7.parse(
                    "MSH|^~\&|TOTO|TUTU|SOFTNAME|CHABC|201602011049||-------|exp_ANE_5|P|2.3.1\rPID|1||8123456DK01||DUPONT^ALBERT ANTHONY|||||||||||||123456")
                response = client.send(hl7_other_request)
                hl7_response = hl7.parse(response)

                self.assertEqual('AR', hl7_response['MSA.1'])
                self.assertEqual('No Handler found for message type -------', hl7_response['MSA.3'])

    def test_new_doc_message(self): # non-regression test because, at some point, the last segment was considered invalid by the client
        port_number = 2103  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)

        # start a server that will echo all ORU^R01 messages and return an error message for all other message types
        with MLLPServer('localhost', port_number, {
            'ORU^R01': (hl7_echo_message_handler,),
            'ERR': (hl7_default_error_handler,)
        }) as server:

            # validate that the newDoc message is echoed
            with MLLPClient('localhost', port_number) as client:
                hl7_oru_r01_request = hl7.parse(
                    "MSH|^~\&|INTERHOSP|OSIMIS|NEWDOC|CHR|201612051719||ORU^R01|634017193866620135CX|P|2.3.1|||AL|AL|BE|ASCII\rPID|1||9011071DJ01|||DOE^JOHN\rOBR|1||000000001|RXD|||201301081234||||||||||||||||||P||||||||\rOBX|1|ED|DICTEE||CITAPOLUS^APPLICATION^TXT^^Protocole réalisé à partir de InterHosp.\\.br\\Seule l'image est disponible via l'interface web\\.br\\"
                )

                response = client.send(hl7_oru_r01_request)
                hl7_response = hl7.parse(response)
                self.assertEqual(hl7_oru_r01_request, hl7_response)

            with MLLPClient('localhost', port_number) as client:

                # same test by constructing the message another way
                MSH = hl7.Segment(hl7Lib.HL7_FIELD_SEPARATOR, [hl7.Field(hl7Lib.HL7_ALL_SEPARATORS[1], ['MSH'])])
                PID = hl7.Segment(hl7Lib.HL7_FIELD_SEPARATOR, [hl7.Field(hl7Lib.HL7_ALL_SEPARATORS[1], ['PID'])])
                OBR = hl7.Segment(hl7Lib.HL7_FIELD_SEPARATOR, [hl7.Field(hl7Lib.HL7_ALL_SEPARATORS[1], ['OBR'])])
                hl7_message = hl7.Message(b'\x0d'.decode(), [MSH, PID, OBR])

                # MSH reference: https://www.hl7.org/documentcenter/public_temp_1D5D9D29-1C23-BA17-0CDBD1CAA8621C11/wg/conf/HL7MSH.htm
                hl7_message['MSH.F1.R1'] = hl7Lib.HL7_FIELD_SEPARATOR
                hl7_message['MSH.F2.R1'] = hl7Lib.HL7_ALL_SEPARATORS[1:]
                hl7_message['MSH.F3.R1'] = 'INTERHOSP'  # sending application
                hl7_message['MSH.F4.R1'] = 'OSIMIS'
                hl7_message['MSH.F5.R1'] = 'NEWDOC'
                hl7_message['MSH.F6.R1'] = 'CHR'
                hl7_message['MSH.F7.R1'] = strftime('%Y%m%d%H%M')
                hl7_message['MSH.F9.R1.C1'] = 'ORU'
                hl7_message['MSH.F9.R1.C2'] = 'R01'
                hl7_message['MSH.F10.R1'] = hl7.generate_message_control_id()
                hl7_message['MSH.F11.R1'] = 'P'  # processing ID
                hl7_message['MSH.F12.R1'] = '2.3.1'
                hl7_message['MSH.F15.R1'] = 'AL'  # Accept acknowledgment type (AL = Always)
                hl7_message['MSH.F16.R1'] = 'AL'  # Application acknowledgment type
                hl7_message['MSH.F17.R1'] = 'BE'  # Country Code
                hl7_message['MSH.F18.R1'] = 'ASCII'  # Character set

                hl7_message['PID.F1.R1'] = '1'  # Set ID
                hl7_message['PID.F3.R1'] = '9011071DJ01'
                hl7_message['PID.F6.R1'] = 'DOE^JOHN'

                hl7_message['OBR.F1.R1'] = '1'  # Set ID
                hl7_message['OBR.F3.R1'] = re.sub("\D", "",'IHPCHU0000001')  # keep only the digits in the accessionNumber    '{{{uuid}}}'.format(uuid = str(uuid.uuid1())) # accessionNumber    # filler order number  must be either a 40bit number or a windows guid {43495441-4445-4C4C-4500-110036216380}.  CHU000000001 is not a valid id
                hl7_message['OBR.F4.R1'] = 'RXD'  # universalServiceId
                hl7_message['OBR.F7.R1'] = '201301081234'
                hl7_message['OBR.F25.R1'] = 'P'  # result status: F=final, P=preliminary
                hl7_message['OBR.F33.R1'] = ''  # 'TODO'        # principalResultInterpreter TODO: define with CHR

                obxIndex = 1
                OBX = hl7.Segment(hl7Lib.HL7_FIELD_SEPARATOR, [hl7.Field(hl7Lib.HL7_ALL_SEPARATORS[1], ['OBX'])])
                hl7_message.append(OBX)
                hl7_message['OBX{0}.F1.R1'.format(obxIndex)] = '1'  # Set ID
                hl7_message['OBX{0}.F2.R1'.format(obxIndex)] = 'ED'  # FT,ST,TX = text, ED = encapsulated data, RP = Reference pointer to a file
                hl7_message['OBX{0}.F3.R1'.format(obxIndex)] = 'DICTEE'
                hl7_message['OBX{0}.F5'.format(obxIndex)] = "CITAPOLUS^APPLICATION^TXT^^Protocole réalisé à partir de InterHosp.\\.br\\Seule l'image est disponible via l'interface web\\.br\\"

                response = client.send(hl7_message)
                hl7_response = hl7.parse(response)
                self.assertEqual(str(hl7_message), str(hl7_response))


    def test_message_one_byte_at_a_time(self): # Avignon sends the first byte then, the rest of the message -> this made our server crash
        port_number = 2104  # there are currently some issues when trying to reuse the same port in 2 tests (it's probably not freed soon enough -> let's use another port for each test)

        # start a server that will echo all ORU^R01 messages and return an error message for all other message types
        with MLLPServer('localhost', port_number, {
            'ORU^R01': (hl7_echo_message_handler,),
            'ERR': (hl7_default_error_handler,)
        }) as server:

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('localhost', port_number))
            s.send(b'\x0b')
            bytes_message = "MSH|^~\&|TOTO|TUTU|SOFTNAME|CHABC|201602011049||ORU^R01|exp_ANE_5|P|2.3.1\rPID|1||8123456DK01||DUPONT^ALBERT ANTHONY|||||||||||||123456\r".encode('iso-8859-1')
            s.send(bytes_message)
            s.send(b'\x1c')
            s.send(b'\x0d')

            response = s.recv(5) # just check the first part of the response
            self.assertEqual(b'\x0bMSH|', response)
            s.close()
