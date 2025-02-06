from datetime import datetime
import random
import socketserver, subprocess, sys, re, socket
from threading import Thread
#from hl7Lib import Hl7MessageValidator, UnsupportedMessageType, InvalidHL7Message
from .hl7_message_validator import Hl7MessageValidator
from .hl7_error import UnsupportedMessageType, InvalidHL7Message
import hl7
import logging

logger = logging.getLogger(__name__)

#
# class UnsupportedMessageType(Exception):
#     """
#     Error that occurs when the :class:`MLLPServer` receives a message without an associated handler
#     """
#
#     def __init__(self, msgType):
#         self.msg_type = msgType
#
#     def __str__(self):
#         return 'No Handler found for message type %s' % self.msgType
#
#
# class InvalidHL7Message(Exception):
#     """
#     Error that occurs when the :class:`MLLPServer` receives a string which doesn't represent an ER7-encoded HL7 message
#     """
#
#     def __init__(self, msg):
#         self.msg = msg
#
#     def __str__(self):
#         return 'The string received is not a valid HL7 message : {0}'.format(self.msg)
#

class _Hl7MllpRequestHandler(socketserver.StreamRequestHandler):
    """
    Internal class: implements the request handler
    """

    def setup(self, encoding: str = 'iso-8859-1'):
        self.encoding = encoding
        self.sb = b'\x0b'
        self.eb = b'\x1c'
        self.cr = b'\x0d'
        self.timeout = self.server.timeout
        self._handlers = self.server._handlers
        self._validator = Hl7MessageValidator(encoding = encoding, sb = self.sb, eb = self.eb, cr = self.cr)

        socketserver.StreamRequestHandler.setup(self)

    def handle(self):
        end_seq = self.eb + self.cr  # end sequence for the MLLP message
        try:
            # receive the first 3 char of the byte stream (an MLLP HL7 message must at least be 3 chars long (the sb, eb and cr)
            bline = self.rfile.read(3)
        except socket.timeout:
            self.request.close()
            return

        if len(bline) < 3: # in case the client did not send a complete message
            return

        # check the first char of the MLLP message
        if bline[0] != self.sb[0]:
            self.request.close()
            return

        # receive chars one by one until we reach the end sequence
        while bline[-2:] != end_seq:
            try:
                char = self.rfile.read(1)
                if not char:
                    break
                bline += char
            except socket.timeout:
                self.request.close()
                return

        # convert the byte stream to string and try to extract a valid HL7 message out of it
        message = self._validator.validate(bline)
        if message is not None:
            try:
                response = self._route_message(message)
            except Exception as e:
                self.request.close()
            else:
                # encode the response
                if isinstance(response, hl7.Message):
                    self.wfile.write(self.sb + (str(response)).encode(self.encoding) + self.eb + self.cr)
                else:
                    self.wfile.write(self.sb + response + self.eb + self.cr)
        self.request.close()

    def _route_message(self, msg):
        try:
            try:
                msgType = msg.split('|')[8]  # message type is the 9th element of MSH segment (assumed to be the first segment)
            except Exception:
                raise InvalidHL7Message(msg = msg)

            try:
                handler, args = self._handlers[msgType][0], self._handlers[msgType][1:]
            except KeyError:
                logger.warning(f"Unsupported message type '{msgType}'")
                raise UnsupportedMessageType(msgType)

            # create a new handler and call the constructor with the args provided
            return handler(msg, *args)
        except Exception as e:
            try:
                errHandler, args = self._handlers['ERR'][0], self._handlers['ERR'][1:]
            except KeyError:
                raise e
            else:
                response = errHandler(msg, error_description = str(e), *args)
                return response


def run_server_in_separate_thread(server):
    server.serve_forever()


class MLLPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
        A :class:`TCPServer <SocketServer.TCPServer>` subclass that implements an MLLP server.
        It receives MLLP-encoded HL7 and redirects them to the correct handler, according to the
        :attr:`handlers` dictionary passed in.

        The :attr:`handlers` dictionary is structured as follows. Every key represents a message type (i.e.,
        the MSH.9) to handle, and the associated value is a tuple containing a subclass of
        :class:`AbstractHandler` for that message type and additional arguments to pass to its
        constructor.

        It is possible to specify a special handler for errors using the ``ERR`` key.
        In this case the handler should subclass :class:`AbstractErrorHandler`,
        which receives, in addition to other parameters, the raised exception as the first argument.
        If the special handler is not specified the server will just close the connection.

        The class allows to specify the timeout to wait before closing the connection.

        :param host: the address of the listener (use '0.0.0.0' to accept connections from anywhere)
        :param port: the port of the listener
        :param handlers: the dictionary that specifies the handler classes for every kind of supported message.
        :param timeout: the timeout for the requests
    """
    allow_reuse_address = True

    def __init__(self, host, port, handlers, timeout = 10):
        self.host = host
        self.port = port
        self._handlers = {
            'ERR': (handle_error_message,)
            }
        self.add_handlers(handlers)

        self.timeout = timeout
        self.thread = None
        self._is_running = False
        super().__init__((host, port), _Hl7MllpRequestHandler)

    def add_handlers(self, handlers: dict):
        """
        Allow to add handler(s) to an existing server.
        No restart is needed.

        Use example:
        mllp_server = MLLPServer(
                    host = 'localhost',
                    port = 2575,
                    handlers = {
                    'ERR': (orm_handler.handle_error_message,)
                    },
                    logger = logging.getLogger('WORKLIST SERVER')
            )
        mllp_server.add_handler({'ORM^O01': (orm_handler.handle_orm_message,)})
        """
        self._handlers.update(handlers)

    def serve_forever(self):
        self._is_running = True
        logger.info("Starting MLLP Server listening on port {port}".format(port = self.port))
        socketserver.TCPServer.serve_forever(self)
        logger.info("Stopping MLLP Server")
        self._is_running = False

    def start(self):
        """ run the server in a separate thread
        call server.stop() from another thread to stop the server
        """
        self.thread = Thread(target = run_server_in_separate_thread, args = (self,))
        self.thread.start()

    def stop(self):
        """stops a server that has been started with start()"""

        if self.thread is not None:
            self.shutdown()
            self.thread.join()
            self.thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def is_running(self):
        return self._is_running


def default_message_handler(message):
    return NotImplementedError("Please implement a message handler.")

def handle_error_message(self, message: str, error_description: str = None) -> hl7.Message:

    hl7_request = hl7.parse(message)  # we need to re-parse it here only the build the response

    hl7_response = hl7.parse('MSH|^~\&|{sending_application}||{receiving_application}|{receiving_facility}|{date_time}||ACK^O01|{ack_message_id}|P|2.3||||||8859/1\rMSA|AR|{message_id}|{error}'.format(  # TODO: handle encoding
        sending_application = hl7_request['MSH.F5.R1.C1'],
        receiving_application = hl7_request['MSH.F3.R1.C1'],
        receiving_facility = hl7_request['MSH.F4.R1.C1'],
        date_time = datetime.now().strftime("%Y%m%d%H%M%S"),
        message_id = hl7_request['MSH.F10.R1.C1'],
        ack_message_id = str(random.randrange(0, 10 ** 15)),
        error = error_description
    ))
    return hl7_response

# this is just a very quick usage example that does nothing usefull since it uses abstract handler
if __name__ == "__main__":
    # server = Hl7Server(port = 2575, requestHandler = Hl7BaseRequestHandler)
    server = MLLPServer('localhost', 2575, {
        'ORU^R01': (default_message_handler,),
        'ERR': (handle_error_message,)
    })
    # terminate with Ctrl-C
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
