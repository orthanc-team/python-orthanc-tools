import os
from .hl7_report_parser import Hl7ReportParser
from .hl7_report_series_builder import ReportSeriesBuilder
from .hl7_ack import build_acknowledgement
import hl7
import logging

logger = logging.getLogger(__name__)


class Hl7OruReportMsgHandler:

    def __init__(self,
                 parser: Hl7ReportParser,
                 builder: ReportSeriesBuilder,
                 encoding: str = 'ascii'  # TODO: currently not used !
                 ):

        logger.info("Creating ORU report message handler")

        self._parser = parser
        self._builder = builder

    def handle_oru_message(self, message: str) -> hl7.Message:

        # TODO: improve logging as it was done with osimis logger
        # with self._logger.context(str(self._messageCounter)):

        logger.info("received message:{eol}{message}".format(message = str(message).replace('\r', os.linesep), eol = os.linesep))
        hl7_request = hl7.parse(message)  # we need to parse it here only the build the response

        acknowledge_status = "AE"
        error_description = None

        try:
            values = self._parser.parse(hl7_message = message)
            logger.info(f"extracting pdf file... {values['PatientName']}")
            self._builder.generate(values)
            acknowledge_status = "AA"
        except Exception as e:
            logger.error("pdf not added to the study: {exception}".format(exception=e))
            error_description = str(e)

        hl7_response = build_acknowledgement(
            request=hl7_request,
            status=acknowledge_status,
            error_description=error_description,
        )
        logger.info("sending response:{eol}{response}".format(response = str(hl7_response).replace('\r', os.linesep), eol = os.linesep))
        return hl7_response
