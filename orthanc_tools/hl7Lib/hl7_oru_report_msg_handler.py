import os
from .hl7_report_parser import Hl7ReportParser
from .hl7_report_series_builder import ReportSeriesBuilder
import hl7, random
from datetime import datetime
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

        values = self._parser.parse(hl7_message = message)

        succeeded = "AE" # "Application Error", there is a problem processing the message. The sending application must correct the problem before attempting to resend the message.

        try:
            logger.info(f"extracting pdf file... {values['PatientName']}")
            self._builder.generate(values)
            succeeded = "AA" # Positive acknowledgment: the message was successfully processed.
        except Exception as e:
            logger.error("pdf not added to the study: {exception}".format(exception=e))

        hl7_response = hl7.parse('MSH|^~\&|{sending_application}||{receiving_application}|{receiving_facility}|{date_time}||ACK^O01|{ack_message_id}|P|2.3||||||8859/1\rMSA|{acknowledge_status}|{message_id}'.format(  # TODO: handle encoding
            sending_application = hl7_request['MSH.F5.R1.C1'],
            receiving_application = hl7_request['MSH.F3.R1.C1'],
            receiving_facility = hl7_request['MSH.F4.R1.C1'],
            date_time = datetime.now().strftime("%Y%m%d%H%M%S"),
            message_id = hl7_request['MSH.F10.R1.C1'],
            acknowledge_status = succeeded,
            ack_message_id = str(random.randrange(0, 10**15))
        ))
        logger.info("sending response:{eol}{response}".format(response = str(hl7_response).replace('\r', os.linesep), eol = os.linesep))
        return hl7_response
