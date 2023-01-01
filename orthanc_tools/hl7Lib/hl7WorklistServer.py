import os, argparse, sys
from .hl7WorklistParser import Hl7WorklistParser
from .dicomWorklistBuilder import DicomWorklistBuilder
from .hl7Server import MLLPServer
import hl7, random
from datetime import datetime
import logging

from orthanc_tools import OldFilesDeleter


class Hl7WorklistServer(MLLPServer):
    def __init__(self,
                 port: int,
                 parser: Hl7WorklistParser,
                 builder: DicomWorklistBuilder,
                 host: str = '0.0.0.0',
                 logger: logging.Logger = logging.getLogger('Hl7WorklistServer'),
                 automatic_deletion_delay: float = None,  # None = no automatic deletion of files
                 encoding: str = 'ascii'  # TODO: currently not used !
                 ):
        super().__init__(host = host,
                         port = port,
                         logger = logger,
                         handlers = {
            'ORM^O01': (self.handle_orm_message,),
            'ERR': (self.handle_error_message,)
        })

        assert builder._folder is not None, "You must provide a DicomWorklistBuilder with a folder defined"
        self._logger.info("Creating HL7 Worklist server listening on {host}:{port}".format(host = host, port = port))

        self._parser = parser
        self._builder = builder
        self._message_counter = 0
        if automatic_deletion_delay is not None:
            self._logger.info("Automatic deletion of files enabled (after {n} seconds)".format(n = automatic_deletion_delay))
            self._old_files_deleter = OldFilesDeleter(folder_to_monitor = builder.get_folder(),
                                                    timeout = automatic_deletion_delay,
                                                    execution_interval = automatic_deletion_delay/10.0,
                                                    logger = logger
                                                    )
        else:
            self._logger.info("Automatic deletion of files disabled")
            self._old_files_deleter = None


    def start(self):
        super().start()
        if self._old_files_deleter:
            self._old_files_deleter.start()


    def stop(self):
        super().stop()
        if self._old_files_deleter:
            self._old_files_deleter.stop()

    # TODO: this seems not to work -> to investigate
    # def serveForever(self):
    #     if self._old_files_deleter:
    #         self._old_files_deleter.start()
    #     self.serve_forever()

    def handle_orm_message(self, message: str) -> hl7.Message:
        self._message_counter += 1

        # TODO: improve logging as it was done with osimis logger
        # with self._logger.context(str(self._messageCounter)):

        self._logger.info("received message:{eol}{message}".format(message = str(message).replace('\r', os.linesep), eol = os.linesep))
        hl7_request = hl7.parse(message)  # we need to parse it here only the build the response

        values = self._parser.parse(hl7_message = message)
        worklistFilePath = self._builder.generate(values)
        self._logger.info("generated file: {path}".format(path = worklistFilePath))

        hl7_response = hl7.parse('MSH|^~\&|{sending_application}||{receiving_application}|{receiving_facility}|{date_time}||ACK^O01|{ack_message_id}|P|2.3||||||8859/1\rMSA|AA|{message_id}'.format(  # TODO: handle encoding
            sending_application = hl7_request['MSH.F5.R1.C1'],
            receiving_application = hl7_request['MSH.F3.R1.C1'],
            receiving_facility = hl7_request['MSH.F4.R1.C1'],
            date_time = datetime.now().strftime("%Y%m%d%H%M%S"),
            message_id = hl7_request['MSH.F10.R1.C1'],
            ack_message_id = str(random.randrange(0, 10**15))
        ))
        self._logger.info("sending response:{eol}{response}".format(response = str(hl7_response).replace('\r', os.linesep), eol = os.linesep))
        return hl7_response

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



# this is just a very quick usage example that starts a hl7 worklist server
if __name__ == "__main__":

    # build command line parser
    parser = argparse.ArgumentParser(description = 'Create a simple HL7 Dicom Worklist server')
    parser.add_argument('-p', '--port', help = 'Port number the HL7 Server will listen to', default = 2575, type = int)
    parser.add_argument('-f', '--folder', help = 'Folder in which the HL7 Server will store the Dicom Worklist files (.wl).  This folder shall be the one Orthanc uses as its WorklistDatabase')
    parser.add_argument('-e', '--encoding', help = 'The encoding of HL7 messages', default = 'iso-8859-1')

    args = parser.parse_args()

    parser = Hl7WorklistParser()
    builder = DicomWorklistBuilder(folder = args.folder)
    server = Hl7WorklistServer(
        parser = parser,
        builder = builder,
        port = args.port,
        logger = logging.getLogger('HL7 WORKLIST SERVER'),
        encoding = args.encoding
    )

    # terminate with Ctrl-C
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
