from optparse import OptionParser

import hl7
import typing
import os.path
import six
import socket
import sys
from .hl7_message_validator import Hl7MessageValidator


class MLLPClient:
    """
    A basic, blocking, HL7 MLLP client based upon :py:mod:`socket`.

    Can be used by the ``with`` statement to ensure :py:meth:`MLLPClient.close`
    is called::

        with MLLPClient(host, port) as client:
            client.send(msg)
    """
    def __init__(self, host: str, port: int, encoding: str = 'iso-8859-1'):
        self.encoding = encoding
        self.sb = b'\x0b' # <SB>, vertical tab
        self.eb = b'\x1c' # <EB>, file separator
        self.cr = b'\r' # <CR>, \r
        self._extractor = Hl7MessageValidator(sb = self.sb, eb = self.eb, cr = self.cr, encoding = encoding)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, trackeback):
        self.close()

    def close(self):
        """Release the socket connection"""
        self.socket.close()

    def _receive(self):
        end_seq = self.eb + self.cr  # end sequence for the MLLP message
        try:
            # receive the first 3 char of the byte stream (an MLLP HL7 message must at least be 3 chars long (the sb, eb and cr)
            bline = self.socket.recv(3)
        except socket.timeout:
            self.request.close()
            return # TODO: throw exception on errors

        if len(bline) == 0: # connection has been closed
            return # TODO: throw exception on errors

        # check the first char of the MLLP message
        if bline[0] != self.sb[0]:
            self.socket.close()
            return # TODO: throw exception on errors

        # receive chars one by one until we reach the end sequence
        while bline[-2:] != end_seq:
            try:
                char = self.socket.recv(1)
                if not char:
                    break
                bline += char
            except socket.timeout:
                self.socket.close()
                return  # TODO: throw exception on errors

        # convert the byte stream to string and try to extract a valid HL7 message out of it
        message = self._extractor.validate(bline)
        self.socket.close()

        return message


    def send(self, message: typing.Union[bytes, bytearray, hl7.Message]):
        """ sends a message to an HL7 server.

        Args:
            message: The message may be an hl7.message or a bytearray.  sb/eb/cr are added around the message

        Returns: a string with the response (without the sb/eb/cr around the message)
        """
        if isinstance(message, hl7.Message):
            self.socket.send(self.sb + (str(message)).encode(self.encoding) + self.cr + self.eb + self.cr)
        elif isinstance(message, (bytes, bytearray)):
            self.socket.send(message)
        else:
            raise TypeError('message should be hl7.Message or a bytearray (bytes)')
        return self._receive()