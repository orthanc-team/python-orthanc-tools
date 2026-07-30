import os, argparse, sys
from .hl7_worklist_parser import Hl7WorklistParser
from .hl7_dicom_worklist_builder import DicomWorklistBuilder
from .hl7_ack import build_acknowledgement
import hl7
import logging

logger = logging.getLogger(__name__)

class Hl7OrmWorklistMsgHandler:

    def __init__(self,
                 parser: Hl7WorklistParser,
                 builder: DicomWorklistBuilder,
                 encoding: str = 'ascii'  # TODO: currently not used !
                 ):

        assert builder._folder is not None or builder._orthanc_client is not None, "You must provide a DicomWorklistBuilder with a folder or an OrthancClient defined!"
        logger.info("Creating ORM worklist message handler")

        self._parser = parser
        self._builder = builder

    def handle_orm_message(self, message: str) -> hl7.Message:

        # TODO: improve logging as it was done with osimis logger
        # with self._logger.context(str(self._messageCounter)):

        logger.info("received message:{eol}{message}".format(message = str(message).replace('\r', os.linesep), eol = os.linesep))
        hl7_request = hl7.parse(message)  # we need to parse it here only the build the response

        acknowledge_status = "AE"
        error_description = None

        try:
            values = self._parser.parse(hl7_message = message)
        except Exception as e:
            logger.error("problem during parsing: {exception}".format(exception=e))
            values = None
            error_description = str(e)

        if values is not None:
            try:
                logger.info(f"generating worklist, ({'file' if self._builder._orthanc_client is None else 'db record'})...")
                r = self._builder.generate(values)
                logger.info(f"generated worklist: {r}")
                acknowledge_status = "AA"
            except Exception as e:
                logger.error("worklist not generated: {exception}".format(exception=e))
                error_description = str(e)

        hl7_response = build_acknowledgement(
            request=hl7_request,
            status=acknowledge_status,
            error_description=error_description,
        )
        logger.info("sending response:{eol}{response}".format(response = str(hl7_response).replace('\r', os.linesep), eol = os.linesep))
        return hl7_response
