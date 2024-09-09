import time, sys
import argparse
import logging
from orthanc_api_client import OrthancApiClient
import os

import schedule

# examples:
# python orthanc_tools/orthanc_warmer.py --url=http://192.168.0.10:8042 --user=user --password=pwd --interval=30


logger = logging.getLogger(__name__)

class OrthancWarmer:
    def __init__(self,
                 api_client: OrthancApiClient,
                 interval: int
                 ):
        self._api_client = api_client
        self._interval = interval
        self._errors_counter = 0

    def find(self):
        try:
            o.studies.find(query={'StudyDate': "19500101"})
            # 1st of January 1950 is sunday, so probably no results
            self._errors_counter = 0
            logger.debug("Find succeeded!")

        except Exception as ex:
            self._errors_counter += 1
            logger.error(f"{str(ex)}")
            if self._errors_counter > 5:
                logger.error("Last 5 queries to Orthanc failed, so exiting...")
                sys.exit()


    def execute(self):
        logger.info("----- Initializing Orthanc Warmer...")
        schedule.every(interval).minutes.do(self.find)

        while True:
            schedule.run_pending()
            time.sleep(1)

if __name__ == '__main__':
    level = logging.INFO
    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Periodically queries Orthanc to keep the database warm.')
    parser.add_argument('--url', type=str, default='http://localhost:8042', help='Orthanc url')
    parser.add_argument('--user', type=str, default=None, help='Orthanc user name')
    parser.add_argument('--password', type=str, default=None, help='Orthanc password')
    parser.add_argument('--api_key', type=str, default=None, help='Orthanc api-key')
    parser.add_argument('--interval', type=int, default=30, help='Period of time between 2 queries (minutes).')
    args = parser.parse_args()

    url = os.environ.get("ORTHANC_URL", args.url)
    user = os.environ.get("ORTHANC_USER", args.user)
    password = os.environ.get("ORTHANC_PWD", args.password)
    api_key = os.environ.get("ORTHANC_API_KEY", args.api_key)
    interval = int(os.environ.get("INTERVAL", args.interval))

    o = None
    if api_key is not None:
        o=OrthancApiClient(url, headers={"api-key":api_key})
    else:
        o=OrthancApiClient(url, user=user, pwd=password)

    warmer = OrthancWarmer(api_client=o, interval=interval)
    warmer.execute()