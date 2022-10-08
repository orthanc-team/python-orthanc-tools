import time
import sys
import pprint
import unittest
import subprocess
import tempfile
import datetime
from threading import Timer
import shutil
import logging
from orthanc_api_client import OrthancApiClient, ChangeType
from orthanc_api_client import helpers
import orthanc_api_client.exceptions as api_exceptions
import pathlib
import os
import logging

from orthanc_tools import OrthancCloner, ClonerMode, OrthancMonitor, OrthancTestDbPopulator, PacsMigrator, OrthancComparator

here = pathlib.Path(__file__).parent.resolve()

logger = logging.getLogger('orthanc_tools')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class Test3Orthancs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker-compose", "down", "-v"], cwd=here/"docker-setup")
        subprocess.run(["docker-compose", "up", "-d"], cwd=here/"docker-setup")

        cls.oa = OrthancApiClient('http://localhost:10042', user='test', pwd='test')
        cls.oa.wait_started()
        cls.ob = OrthancApiClient('http://localhost:10043', user='test', pwd='test')
        cls.ob.wait_started()
        cls.oc = OrthancApiClient('http://localhost:10044', user='test', pwd='test')
        cls.oc.wait_started()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker-compose", "down", "-v"], cwd=here/"docker-setup")

    def test_cloner_default(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        cloner = OrthancCloner(source=self.oa, destination=self.ob)
        cloner.execute()

        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

    def test_cloner_transfer(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        cloner = OrthancCloner(source=self.oa, destination_peer='orthanc-b', mode=ClonerMode.TRANSFER)
        time.sleep(5) # wait for StableStudy event
        cloner.execute()

        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

    def test_cloner_peering(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        cloner = OrthancCloner(source=self.oa, destination_peer='orthanc-b', mode=ClonerMode.PEERING)
        cloner.execute()

        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

    def test_monitor(self):
        self.oa.delete_all_content()
        processed_instances = []

        monitor = OrthancMonitor(
            self.oa,
            polling_interval=0.1
        )

        def new_instance_handler(change_id, instance_id, api_client):
            processed_instances.append(instance_id),

        monitor.add_handler(ChangeType.NEW_INSTANCE, new_instance_handler)

        monitor.start()

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        helpers.wait_until(lambda: len(processed_instances) > 0, 30)

        monitor.stop()
        self.assertEqual(1, len(processed_instances))

    def test_populator_repeatability(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        populator_a = OrthancTestDbPopulator(api_client=self.oa, studies_count=2, random_seed=42)
        populator_b = OrthancTestDbPopulator(api_client=self.ob, studies_count=2, random_seed=42)

        populator_a.execute()
        populator_b.execute()

        self.assertEqual(self.oa.instances.get_all_ids(), self.ob.instances.get_all_ids())


    def test_monitor_recovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            persist_status_path = os.path.join(temp_dir, 'seq.txt')

            processed_resources = []

            def process_instance(change_id, instance_id, api_client):
                logger.info(f'processing instance {instance_id}')
                time.sleep(5)
                processed_resources.append(instance_id)

            def process_series(change_id, series_id, api_client):
                logger.info(f'processing series {series_id}')
                processed_resources.append(series_id)

            monitor = OrthancMonitor(
                self.oa,
                polling_interval=0.1,
                persist_status_path=persist_status_path,
                worker_threads_count=4
            )

            # first event is lengthy (5 seconds) and will not be processed at the time we first check the sequence id file
            monitor.add_handler(ChangeType.NEW_INSTANCE, process_instance)
            monitor.add_handler(ChangeType.NEW_SERIES, process_series)

            self.oa.upload_file(here / "stimuli/CT_small.dcm")

            monitor.start()
            helpers.wait_until(lambda: len(processed_resources) > 0, 1)
            helpers.wait_until(lambda: os.path.exists(persist_status_path), 1)
            with open(persist_status_path, "rt") as f:
                seq_id = int(f.read())

            all_changes, last_seq_id, done = self.oa.get_changes()
            all_series_ids = self.oa.series.get_all_ids()
            all_instances_ids = self.oa.instances.get_all_ids()

            self.assertGreaterEqual(all_changes[0].sequence_id, seq_id)        # change '1' has not been processed yet
            self.assertEqual(all_series_ids[0], processed_resources[0])     # change '2' has been processed
            self.assertEqual(1, len(processed_resources))  # the instance has not been processed yet because of the sleep 5

            monitor.stop()

            helpers.wait_until(lambda: len(processed_resources) == 2, 6)
            self.assertEqual(2, len(processed_resources))  # the instance should have been processed by now

            with open(persist_status_path, "rt") as f:
                seq_id = int(f.read())

            self.assertLessEqual(all_changes[-1].sequence_id, seq_id)        # all changes have been processed

    def test_pacs_migrator_orthanc_as_source(self):
        self.oa.delete_all_content()  # source & migrator
        self.ob.delete_all_content()  # destination

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        migrator = PacsMigrator(
            api_client=self.oa,
            destination_modality="orthanc-b",
            from_study_date=datetime.date(2004, 1, 18),
            to_study_date=datetime.date(2004, 1, 20),
            delete_from_source=False
        )
        migrator.execute()

        # check all instances have been transferred and are still on the source
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

    def test_pacs_migrator_orthanc_as_source_reverse(self):
        self.oa.delete_all_content()  # source & migrator
        self.ob.delete_all_content()  # destination

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        migrator = PacsMigrator(
            api_client=self.oa,
            destination_modality="orthanc-b",
            from_study_date=datetime.date(2004, 1, 20),
            to_study_date=datetime.date(2004, 1, 18),
            delete_from_source=False
        )
        migrator.execute()

        # check all instances have been transferred and are still on the source
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))


    def test_pacs_migrator_orthanc_as_source_delete_from_source(self):
        self.oa.delete_all_content()  # source & migrator
        self.ob.delete_all_content()  # destination

        populator_a = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=5,
            random_seed=42,
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25)
        )
        populator_a.execute()

        init_instances_ids = self.oa.instances.get_all_ids()

        migrator = PacsMigrator(
            api_client=self.oa,
            destination_modality="orthanc-b",
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25),
            delete_from_source=True
        )
        migrator.execute()

        # check all instances have been transferred and have been deleted from the source
        self.assertEqual(len(init_instances_ids), len(self.ob.instances.get_all_ids()))
        self.assertEqual(0, len(self.oa.instances.get_all_ids()))


    def test_pacs_migrator_aside(self):
        self.oa.delete_all_content()  # source
        self.ob.delete_all_content()  # migrator
        self.oc.delete_all_content()  # destination

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        migrator = PacsMigrator(
            api_client=self.ob,
            source_modality="orthanc-a",
            destination_aet="ORTHANC-C",
            from_study_date=datetime.date(2004, 1, 18),
            to_study_date=datetime.date(2004, 1, 20)
        )
        migrator.execute()

        # check all instances have been transferred and are still on the source
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.oc.instances.get_all_ids()))

    def test_pacs_migrator_as_destination(self):
        self.oa.delete_all_content()  # source
        self.ob.delete_all_content()  # migrator & destination

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        migrator = PacsMigrator(
            api_client=self.ob,
            source_modality="orthanc-a",
            destination_aet="ORTHANC-B",
            from_study_date=datetime.date(2004, 1, 18),
            to_study_date=datetime.date(2004, 1, 20)
        )
        migrator.execute()

        # check all instances have been transferred and are still on the source
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

    def test_orthanc_comparator_as_a_migrator(self):
        self.oa.delete_all_content()  # source & migrator
        self.ob.delete_all_content()  # destination

        # populate Orthanc A & B with 2 DBs
        populator_a = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=5,
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25)
        )
        populator_a.execute()

        populator_b = OrthancTestDbPopulator(
            api_client=self.ob,
            studies_count=5,
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25)
        )
        populator_b.execute()

        # transfer a few instances randomly before launching the comparator to make sur it acts correctly on incomplete series ...
        instances_a = self.oa.instances.get_all_ids()
        instances_b = self.ob.instances.get_all_ids()
        self.oa.modalities.send('orthanc-b', [instances_a[0], instances_a[2], instances_a[4]])
        self.ob.modalities.send('orthanc-a', [instances_b[0], instances_b[2], instances_b[4]])

        # run the comparator with B as the modality and make sure
        # everything in A goes to B
        comparator = OrthancComparator(
            api_client=self.oa,
            modality='orthanc-b',
            level='Instance',
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25),
            ignore_missing_from_orthanc=True,
            transfer_missing_to_modality=True
        )
        comparator.execute()

        # B should have both studies from A & B while A should stay untouched (except for the few instances transferred)
        self.assertEqual(10, len(self.ob.studies.get_all_ids()))
        self.assertNotEqual(10, len(self.oa.studies.get_all_ids()))

        # run the comparator with B as the modality and make sure
        # everything in B goes to A
        comparator = OrthancComparator(
            api_client=self.oa,
            modality='orthanc-b',
            level='Instance',
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25),
            ignore_missing_on_modality=True,
            retrieve_missing_from_orthanc=True
        )
        comparator.execute()

        # now both orthanc should have full dataset
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main()

