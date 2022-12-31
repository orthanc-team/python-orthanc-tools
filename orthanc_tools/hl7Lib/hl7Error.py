import os


class Hl7Error(Exception):
    def __init__(self, message, hl7_request = None, hl7_response = None):
        self.message = message
        self.hl7_request = hl7_request
        self.hl7_response = hl7_response

    def __str__(self):
        return os.linesep.join(['HL7 client exception: {0}'.format(self.message),
                                'request = {0}'.format(str(self.hl7_request).replace('\r', os.linesep)),
                                'response = {0}'.format(str(self.hl7_response).replace('\r', os.linesep))])


class UnsupportedMessageType(Exception):
    """
    Error that occurs when the :class:`MLLPServer` receives a message without an associated handler
    """

    def __init__(self, msgType):
        self._msgType = msgType

    def __str__(self):
        return 'No Handler found for message type %s' % self._msgType


class InvalidHL7Message(Exception):
    """
    Error that occurs when the :class:`MLLPServer` receives a string which doesn't represent an ER7-encoded HL7 message
    """

    def __init__(self, msg):
        self._msg = msg

    def __str__(self):
        return 'The string received is not a valid HL7 message : {0}'.format(self._msg)
