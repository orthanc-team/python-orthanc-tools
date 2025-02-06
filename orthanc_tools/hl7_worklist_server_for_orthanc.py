import os, argparse, sys, time
from orthanc_tools import MLLPServer, OldFilesDeleter
from orthanc_tools import Hl7WorklistParser, DicomWorklistBuilder, Hl7OrmWorklistMsgHandler
from orthanc_tools import Hl7ReportParser, ReportSeriesBuilder, Hl7OruReportMsgHandler
from orthanc_api_client import OrthancApiClient

import logging

# this starts an hl7 server
if __name__ == "__main__":


    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # build command line parser
    parser = argparse.ArgumentParser(description = 'Create a HL7 server')
    parser.add_argument('-p', '--port', help = 'Port number the HL7 Server will listen to', default = 2575, type = int)
    parser.add_argument('-f', '--folder', help = 'Folder in which the HL7 Server will store the Dicom Worklist files (.wl).  This folder shall be the one Orthanc uses as its WorklistDatabase', default = 'worklists')
    parser.add_argument('-e', '--encoding', help = 'The encoding of HL7 messages', default = 'iso-8859-1')
    parser.add_argument('-r', '--retention', help = "Number of hours to keep the WL after it has been generated", default = 24, type = int)

    args = parser.parse_args()

    port = int(os.environ.get("PORT", str(args.port)))
    folder = os.environ.get("FOLDER", args.folder)
    encoding = os.environ.get("ENCODING", args.encoding)
    retention = int(os.environ.get("RETENTION", str(args.retention)))

    # prepare worklists handler (orm)

    orm_parser = Hl7WorklistParser()
    worklist_builder = DicomWorklistBuilder(folder = folder)
    orm_handler = Hl7OrmWorklistMsgHandler(parser=orm_parser, builder=worklist_builder)

    # configure and start MLLP server
    with MLLPServer(
            host = '0.0.0.0',
            port = port,
            handlers = {
                'ORM^O01': (orm_handler.handle_orm_message,),
                'ORM^O01^ORM_O01': (orm_handler.handle_orm_message,)
            }
    ) as mllp_server:

        # configure and start old_files_deleter
        with OldFilesDeleter(folder_to_monitor = folder, timeout = retention*3600.0, filter = '*.wl', execution_interval = 3600.0) as worklist_cleaner:

            while True:
                time.sleep(1)

