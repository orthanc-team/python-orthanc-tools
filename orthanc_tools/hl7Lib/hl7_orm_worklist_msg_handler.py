import os, argparse, sys
from .hl7_worklist_parser import Hl7WorklistParser
from .hl7_dicom_worklist_builder import DicomWorklistBuilder
import hl7, random
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

#TODO: manage the automatic deletion of old files somewhere else


class Hl7OrmWorklistMsgHandler:

    def __init__(self,
                 parser: Hl7WorklistParser,
                 builder: DicomWorklistBuilder,
                 encoding: str = 'ascii'  # TODO: currently not used !
                 ):

        assert builder._folder is not None, "You must provide a DicomWorklistBuilder with a folder defined"
        logger.info("Creating ORM worklist message handler")

        self._parser = parser
        self._builder = builder

    def handle_orm_message(self, message: str) -> hl7.Message:

        # TODO: improve logging as it was done with osimis logger
        # with self._logger.context(str(self._messageCounter)):

        logger.info("received message:{eol}{message}".format(message = str(message).replace('\r', os.linesep), eol = os.linesep))
        hl7_request = hl7.parse(message)  # we need to parse it here only the build the response

        values = self._parser.parse(hl7_message = message)
        try:
            logger.info("generating file...")
            worklistFilePath = self._builder.generate(values)
        except Exception as e:
            logger.error("file not generated: {exception}".format(exception=e))
        logger.info("generated file: {path}".format(path = worklistFilePath))

        hl7_response = hl7.parse('MSH|^~\&|{sending_application}||{receiving_application}|{receiving_facility}|{date_time}||ACK^O01|{ack_message_id}|P|2.3||||||8859/1\rMSA|AA|{message_id}'.format(  # TODO: handle encoding
            sending_application = hl7_request['MSH.F5.R1.C1'],
            receiving_application = hl7_request['MSH.F3.R1.C1'],
            receiving_facility = hl7_request['MSH.F4.R1.C1'],
            date_time = datetime.now().strftime("%Y%m%d%H%M%S"),
            message_id = hl7_request['MSH.F10.R1.C1'],
            ack_message_id = str(random.randrange(0, 10**15))
        ))
        logger.info("sending response:{eol}{response}".format(response = str(hl7_response).replace('\r', os.linesep), eol = os.linesep))
        return hl7_response
