import unittest
import subprocess
import logging
from orthanc_api_client import OrthancApiClient
import orthanc_api_client.exceptions as api_exceptions
import pathlib
import os
from orthanc_tools import OrthancCloner

here = pathlib.Path(__file__).parent.resolve()



class Test2Orthancs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker-compose", "down", "-v"], cwd=here/"docker-setup")
        subprocess.run(["docker-compose", "up", "-d"], cwd=here/"docker-setup")

        cls.oa = OrthancApiClient('http://localhost:10042', user='test', pwd='test')
        cls.oa.wait_started()
        cls.ob = OrthancApiClient('http://localhost:10043', user='test', pwd='test')
        cls.ob.wait_started()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker-compose", "down", "-v"], cwd=here/"docker-setup")

    def test_cloner(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        self.oa.upload_file( here / "stimuli/CT_small.dcm")

        cloner = OrthancCloner(source=self.oa, destination=self.ob)
        cloner.execute()

        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main()

