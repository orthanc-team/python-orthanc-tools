import sys, os
import time
from threading import Thread
import hl7
import logging
from .hl7_message_parser import Hl7MessageParser
logger = logging.getLogger(__name__)

def run_in_separate_thread(monitor):
    monitor.monitor_folder()

class Hl7FolderMonitor:

    def __init__(self, folder_path, handlers: dict, interval: int = 30):
        '''
        folder_path: the absolute path of the folder which will be monitored (for HL7 files to be found)
        handlers: dict: message type and callback. ex: {'ORM^O01': 'process_message'}
        interval: time (s) between two checks of the folder
        '''
        self._folder_path = folder_path
        # An error message will probably never arrive from a file...
        # self._handlers = {
        #     'ERR': (handle_error_message,)
        #     }
        self._handlers = {}
        self.add_handlers(handlers)
        self._interval = interval
        self.thread = None
        self._is_running = False
        self._parser = Hl7MessageParser()
        self._parser.set_field_definition('message_type', 'MSH.F9')

    def add_handlers(self, handlers: dict):
        self._handlers.update(handlers)

    def clean_file_content(self, file_content):
        '''
        In some cases (Vetera), the HL7 message file contains `\r\n` in place of
        `\r`. here is the replacement.
        '''
        return file_content.replace(b'\r\n', b'\r')

    def monitor_folder(self):
        self._is_running = True

        while self._is_running is True:
            # get files from folder
            for path in os.listdir(self._folder_path):
                full_path = os.path.join(self._folder_path, path)

                # quick parse and call handler if present
                with open(full_path, 'rb') as f:
                    file_content_binary = f.read()
                    file_content_binary = self.clean_file_content(file_content_binary)
                    file_content = file_content_binary.decode('utf-8')
                    message = self._parser.parse(file_content)
                    message_type = message['message_type']
                    if message_type in self._handlers:
                        self._handlers[message_type](file_content)
                    else:
                        logger.error(f"No handler found for {message_type} message. Keeping file for debug...")
                        continue

                # delete file
                os.remove(full_path)

            # wait interval before next check
            time.sleep(self._interval)

        self._is_running = False

    def start(self):
        """ run the server in a separate thread
        call server.stop() from another thread to stop the server
        """
        self.thread = Thread(target = run_in_separate_thread, args = (self,))
        self.thread.start()

    def stop(self):
        """stops a server that has been started with start()"""
        self._is_running = False
        if self.thread is not None:
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

# An error message will probably never arrive from a file...
# def handle_error_message(self, message: str, error_description: str = None) -> hl7.Message:
#
#     hl7_request = hl7.parse(message)  # we need to re-parse it here only the build the response
#
#     hl7_response = hl7.parse('MSH|^~\&|{sending_application}||{receiving_application}|{receiving_facility}|{date_time}||ACK^O01|{ack_message_id}|P|2.3||||||8859/1\rMSA|AR|{message_id}|{error}'.format(  # TODO: handle encoding
#         sending_application = hl7_request['MSH.F5.R1.C1'],
#         receiving_application = hl7_request['MSH.F3.R1.C1'],
#         receiving_facility = hl7_request['MSH.F4.R1.C1'],
#         date_time = datetime.now().strftime("%Y%m%d%H%M%S"),
#         message_id = hl7_request['MSH.F10.R1.C1'],
#         ack_message_id = str(random.randrange(0, 10 ** 15)),
#         error = error_description
#     ))
#     return hl7_response

# this is just a very quick usage example that does nothing usefull since it uses abstract handler
if __name__ == "__main__":
    server = Hl7FolderMonitor('/home/messages', {
        'ORM^O01': (default_message_handler,)
    })
    # terminate with Ctrl-C
    try:
        server.monitor_folder()
    except KeyboardInterrupt:
        sys.exit(0)
