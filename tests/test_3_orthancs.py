import threading
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
import unittest

from orthanc_tools import OrthancCloner, ClonerMode, OrthancMonitor, OrthancTestDbPopulator, PacsMigrator, IdsMigrator, OrthancComparator, OrthancForwarder, ForwarderMode, ForwarderDestination, OrthancCleaner, OrthancFolderImporter, OrthancSyncher

here = pathlib.Path(__file__).parent.resolve()

logger = logging.getLogger('orthanc_tools')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


forwarder_count_failed = 0
forwarder_count_success = 0

class Test3Orthancs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"docker-setup")
        subprocess.run(["docker", "compose", "up", "-d"], cwd=here/"docker-setup")

        cls.oa = OrthancApiClient('http://localhost:10042', user='test', pwd='test')
        cls.oa.wait_started()
        cls.ob = OrthancApiClient('http://localhost:10043', user='test', pwd='test')
        cls.ob.wait_started()
        cls.oc = OrthancApiClient('http://localhost:10044', user='test', pwd='test')
        cls.oc.wait_started()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"docker-setup")

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

    def test_cloner_dicom(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        cloner = OrthancCloner(source=self.oa, destination_dicom='orthanc-b', mode=ClonerMode.DICOM)
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

    def test_populator_repeatability_with_forced_quantities(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        populator_a = OrthancTestDbPopulator(api_client=self.oa, studies_count=2, random_seed=42, series_count=1, instances_count=1)
        populator_b = OrthancTestDbPopulator(api_client=self.ob, studies_count=2, random_seed=42, series_count=1, instances_count=1)

        populator_a.execute()
        populator_b.execute()

        a_ids = self.oa.instances.get_all_ids()
        b_ids = self.ob.instances.get_all_ids()
        self.assertEqual(a_ids, b_ids)
        self.assertEqual(len(a_ids), 2)

    def test_populator_quantities(self):
        self.oa.delete_all_content()

        populator_a = OrthancTestDbPopulator(api_client=self.oa, studies_count=2, series_count=2, instances_count=10, random_seed=42)
        populator_a.execute()

        self.assertEqual(40, len(self.oa.instances.get_all_ids()))


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
            studies_count=3,
            series_count=3,
            instances_count=20,
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

    def test_pacs_migrator_as_destination_c_get(self):
        self.oa.delete_all_content()  # source
        self.ob.delete_all_content()  # migrator & destination

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        migrator = PacsMigrator(
            api_client=self.ob,
            source_modality="orthanc-a",
            destination_aet="ORTHANC-B",
            from_study_date=datetime.date(2004, 1, 18),
            to_study_date=datetime.date(2004, 1, 20),
            use_get_not_move=True
        )
        migrator.execute()

        # check all instances have been transferred and are still on the source
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

    def test_pacs_migrator_exit_on_error(self):
        self.oa.delete_all_content()  # source
        self.ob.delete_all_content()  # migrator & destination

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        with self.assertRaises(SystemExit) as cm:
            migrator = PacsMigrator(
                api_client=self.ob,
                source_modality="orthanc-z",
                destination_aet="ORTHANC-B",
                from_study_date=datetime.date(2004, 1, 18),
                to_study_date=datetime.date(2004, 1, 20),
                exit_on_error=True
            )

            migrator.execute()

        self.assertEqual(cm.exception.code, 1)

    def test_pacs_migrator_wait_for_space(self):

        # We will run this method in another thread to free some space from the destination after a few seconds
        def free_space():
            time.sleep(5)
            self.ob.delete_all_content()

        self.oa.delete_all_content()  # source
        self.ob.delete_all_content()  # migrator & destination

        # let's fill the destination with 7 studies from 322KB so that, the disk use is more than 2MB
        ids = self.ob.upload_file(here / "stimuli/MR/IM-0001-0002.dcm")
        for i in range(6):
            self.ob.studies.anonymize(ids[0], delete_original=False)

        # let's upload one study on Orthanc-a to be migrated
        ids = self.oa.upload_file(here / "stimuli/CT_small.dcm")

        migrator = PacsMigrator(
            api_client=self.ob,
            source_modality="orthanc-a",
            destination_aet="ORTHANC-B",
            from_study_date=datetime.date(2004, 1, 18),
            to_study_date=datetime.date(2004, 1, 20),
            orthanc_space_threshold=1,
            waiting_time_for_space_threshold=10
        )

        # let's plan the freeing of the destination (will happen after 5s)
        thread = threading.Thread(target=free_space)
        thread.start()
        migrator.execute()

        # check that there is now one single instance and it is the one that has been migrated
        self.assertEqual(1, len(self.ob.instances.get_all_ids()))
        self.assertEqual(ids[0], self.ob.instances.get_all_ids()[0])


    def test_ids_migrator_aside(self):
        self.oa.delete_all_content()  # source
        self.ob.delete_all_content()  # migrator
        self.oc.delete_all_content()  # destination

        self.oa.upload_file(here / "stimuli/CT_small.dcm")
        self.oa.upload_file(here / "stimuli//MR/Brain/1/IM0")

        migrator = IdsMigrator(
            api_client=self.ob,
            source_modality="orthanc-a",
            destination_aet="ORTHANC-C",
            ids_list_file_path=here / "stimuli/list.csv"
        )
        migrator.execute()

        # check all instances have been transferred and are still on the source
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.oc.instances.get_all_ids()))

    def test_orthanc_comparator_as_a_migrator(self):
        self.oa.delete_all_content()  # source & migrator
        self.ob.delete_all_content()  # destination

        # populate Orthanc A & B with 2 DBs
        populator_a = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=3,
            series_count=3,
            instances_count=20,
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25)
        )
        populator_a.execute()

        populator_b = OrthancTestDbPopulator(
            api_client=self.ob,
            studies_count=3,
            series_count=3,
            instances_count=20,
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
        self.assertEqual(6, len(self.ob.studies.get_all_ids()))
        self.assertNotEqual(6, len(self.oa.studies.get_all_ids()))

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

    def test_error_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, 'errors.log')
            # check that the errors are logged
            self.oa.delete_all_content()  # source
            self.ob.delete_all_content()  # migrator & destination

            self.oa.upload_file(here / "stimuli/CT_small.dcm")

            # let's make the orthanc b refure c-store requests (to cause an error)
            conf = self.ob.modalities.get_configuration('orthanc-a')
            conf['AllowStore'] = False
            self.ob.modalities.configure('orthanc-a', conf)

            comparator = OrthancComparator(
                api_client=self.ob,
                modality='orthanc-a',
                level='Instance',
                from_study_date=datetime.date(2004, 1, 18),
                to_study_date=datetime.date(2004, 1, 20),
                ignore_missing_on_modality=True,
                retrieve_missing_from_orthanc=True,
                error_log_file_path=path
            )
            comparator.execute()

            self.assertTrue(os.path.exists(path))

            with open(path, "r") as f:
                content = f.readline()

            id, date, level = content.split(',')
            self.assertEqual(id, "1.3.6.1.4.1.5962.1.2.1.20040119072730.12322")
            self.assertEqual(date, "20040119")
            self.assertEqual(level, "study\n")

            # let's restore config for other tets
            conf['AllowStore'] = True
            self.ob.modalities.configure('orthanc-a', conf)


    def test_all_instance_forwarder_modes(self):
        # simple forwarder test without filtering or processing

        for mode in [ForwarderMode.DICOM, ForwarderMode.DICOM_SERIES_BY_SERIES, ForwarderMode.DICOM_WEB, ForwarderMode.DICOM_WEB_SERIES_BY_SERIES, ForwarderMode.PEERING, ForwarderMode.TRANSFER]:
            for trigger in [ChangeType.STABLE_STUDY, ChangeType.STABLE_SERIES, ChangeType.NEW_INSTANCE]:
                self.ob.delete_all_content()  # destination
                self.oa.delete_all_content()  # source

                with OrthancForwarder(source=self.oa,
                                      destinations=[ForwarderDestination(destination="orthanc-b", forwarder_mode=mode)],
                                      trigger=trigger,
                                      polling_interval_in_seconds=0.1) as forwarder:

                    # upload once the forwarder is running
                    instances_ids = self.oa.upload_folder(here / "stimuli/MR/Brain")

                    # wait until the source is empty (= the forwarder has completed its job)
                    helpers.wait_until(lambda: len(self.oa.studies.get_all_ids()) == 0, timeout=30)

                    self.assertEqual(len(instances_ids), len(self.ob.instances.get_all_ids()))
                    # check it has been removed from Orthanc A
                    self.assertEqual(0, len(self.oa.instances.get_all_ids()))

    def test_forwarder_when_orthanc_not_empty_at_startup(self):
        # simple forwarder test without filtering or processing

        for mode in [ForwarderMode.DICOM]:
            for trigger in [ChangeType.STABLE_STUDY, ChangeType.STABLE_SERIES, ChangeType.NEW_INSTANCE]:
                self.ob.delete_all_content()  # destination
                self.oa.delete_all_content()  # source

                # upload before the forwarder is running
                instances_ids = self.oa.upload_folder(here / "stimuli/MR/Brain")

                with OrthancForwarder(source=self.oa,
                                      destinations=[ForwarderDestination(destination="orthanc-b", forwarder_mode=mode)],
                                      trigger=trigger,
                                      polling_interval_in_seconds=0.1) as forwarder:

                    # wait until the source is empty (= the forwarder has completed its job)
                    helpers.wait_until(lambda: len(self.oa.studies.get_all_ids()) == 0, timeout=30)

                    self.assertEqual(len(instances_ids), len(self.ob.instances.get_all_ids()))
                    # check it has been removed from Orthanc A
                    self.assertEqual(0, len(self.oa.instances.get_all_ids()))


    def test_orthanc_forwarder_filter_and_process(self):
        self.ob.delete_all_content()  # destination
        self.oa.delete_all_content()  # source

        mode = ForwarderMode.DICOM_SERIES_BY_SERIES
        trigger = ChangeType.STABLE_STUDY

        instances_ids = self.oa.upload_folder(here / "stimuli/MR/Brain")

        # keep only the sT2W/FLAIR series, delete other series
        def filter_instance(api_client, instance_id) -> bool:
            return api_client.instances.get(instance_id).series.main_dicom_tags.get('SeriesDescription') == 'sT2W/FLAIR'

        def process_instance(api_client, instance_id):
            modified = api_client.instances.modify(
                instance_id,
                replace_tags={"InstitutionName": "MY", "OtherPatientIDs": "1234"},
                keep_tags=['SOPInstanceUID', 'SeriesInstanceUID', 'StudyInstanceUID'],
                force=True,
            )
            r = api_client.upload(buffer=modified)
            self.assertEqual(r[0], instance_id)

        def on_forwarded(instances_set, destination):
            global forwarder_count_success
            forwarder_count_success = forwarder_count_success + 1

        def on_forward_failed(instances_set, destination, error):
            global forwarder_count_failed
            forwarder_count_failed = forwarder_count_failed + 1

        # Tell the target to reject incoming instances.  Therefore, we will exercise the retries !
        orthanc_a_config = self.ob.modalities.get_configuration(modality='orthanc-a')
        self.ob.modalities.delete(modality='orthanc-a')

        OrthancForwarder.retry_intervals = [1, 2, 3, 4, 5, 6]

        with OrthancForwarder(
            source=self.oa,
            destinations=[ForwarderDestination(destination="orthanc-b", forwarder_mode=mode)],
            trigger=trigger,
            polling_interval_in_seconds=0.1,
            instance_filter=filter_instance,
            instance_processor=process_instance,
            on_instances_set_forwarded=on_forwarded,
            on_instances_set_forward_error=on_forward_failed
            ) as forwarder:

            time.sleep(3)

            # tell the target to accept incoming instances again
            self.ob.modalities.configure(
                modality='orthanc-a',
                configuration=orthanc_a_config
            )

            # wait until the source is empty (= the forwarder has completed its job and deleted them)
            helpers.wait_until(lambda: len(self.oa.studies.get_all_ids()) == 0, timeout=3000)  # TODO: 30 s

            # check only the flair series has arrived on b
            self.assertEqual(1, len(self.ob.instances.get_all_ids()))
            forwarded_instance = self.ob.instances.get(self.ob.instances.get_all_ids()[0])
            self.assertEqual("MY", forwarded_instance.tags.get('InstitutionName'))
            self.assertEqual("1234", forwarded_instance.tags.get('OtherPatientIDs'))
            self.assertEqual("sT2W/FLAIR", forwarded_instance.series.main_dicom_tags.get('SeriesDescription'))

            # check it has been removed from Orthanc A
            self.assertEqual(0, len(self.oa.instances.get_all_ids()))

            # check the callbacks have been called
            self.assertNotEqual(0, forwarder_count_success)
            self.assertNotEqual(0, forwarder_count_failed)

    def test_orthanc_cleaner_with_past_studies(self):
        self.oa.delete_all_content()

        # populate Orthanc with and old study...
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date(1980, 12, 16),
            to_study_date=datetime.date(1983, 12, 16)
        )
        populator.execute()

        old_study_id = self.oa.studies.get_all_ids()[0]

        # ...and a recent study
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today()-datetime.timedelta(days=5),
            to_study_date=datetime.date.today()
        )
        populator.execute()

        # apply a label to one of the 2 studies. This label is NOT in the csv file
        studies_ids = self.oa.studies.get_all_ids()
        self.oa.studies.add_label(studies_ids[0], "LABEL5")

        cleaner = OrthancCleaner(api_client=self.oa, execution_time=None, labels_file_path=here / "stimuli/labels.csv")
        cleaner.execute()

        # check that if no correct label found, studies are kept
        self.assertEqual(len(self.oa.studies.get_all_ids()), 2)


        self.oa.studies.add_label(studies_ids[0], "LABEL2")
        self.oa.studies.add_label(studies_ids[1], "LABEL1")

        cleaner.execute()

        # we would like to check that the recent study is still there and the old one is gone,
        # but given the fact that they have just been uploaded, they should be kept
        self.assertEqual(len(self.oa.studies.get_all_ids()), 2)

    def test_orthanc_cleaner_with_future_studies(self):
        self.oa.delete_all_content()

        # We are not able to trick Orthanc to modify the `LastUpdate` value
        # so let's create studies with dates in the future and
        # a negative retention period

        # populate Orthanc with and "old" future study...
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=3),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=4)
        )
        populator.execute()

        old_study_id = self.oa.studies.get_all_ids()[0]

        # ...and a "recent" future study
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=14),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=16)
        )
        populator.execute()

        studies_ids = self.oa.studies.get_all_ids()

        self.oa.studies.add_label(studies_ids[0], "LABEL3")
        self.oa.studies.add_label(studies_ids[1], "LABEL4")

        cleaner = OrthancCleaner(api_client=self.oa, execution_time=None,
                                 labels_file_path=here / "stimuli/labels.csv")

        cleaner.execute()

        # we would like to check that the recent study is still there and the old one is gone,
        self.assertEqual(len(self.oa.studies.get_all_ids()), 1)
        self.assertNotEqual(old_study_id, self.oa.studies.get_all_ids()[0])

    def test_orthanc_cleaner_with_future_studies_and_filter_on_modality(self):
        self.oa.delete_all_content()

        # We are not able to trick Orthanc to modify the `LastUpdate` value
        # so let's create studies with dates in the future and
        # a negative retention period

        # populate Orthanc with a first "old" future study (CT)
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=3),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=4),
            modality="CT"
        )
        populator.execute()

        ct_study_id = self.oa.studies.get_all_ids()[0]

        # populate Orthanc with a second "old" future study (OT)
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=3),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=4),
            modality="OT"
        )
        populator.execute()

        # populate Orthanc with a third "recent" future study (CT)
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=14),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=16),
            modality="CT"
        )
        populator.execute()

        studies_ids = self.oa.studies.get_all_ids()

        self.oa.studies.add_label(studies_ids[0], "LABEL5")
        self.oa.studies.add_label(studies_ids[1], "LABEL5")
        self.oa.studies.add_label(studies_ids[2], "LABEL5")

        cleaner = OrthancCleaner(api_client=self.oa, execution_time=None,
                                 labels_file_path=here / "stimuli/labels.csv")

        cleaner.execute()

        # we would like to check that the old OT study is still there and the old CT one is gone,
        # while the "recent" CT is also still there
        self.assertEqual(len(self.oa.studies.get_all_ids()), 2)
        self.assertNotEqual(ct_study_id, self.oa.studies.get_all_ids()[0])

    def test_orthanc_cleaner_with_future_studies_and_filter_on_modality_with_2_rules(self):
        self.oa.delete_all_content()

        # We are not able to trick Orthanc to modify the `LastUpdate` value
        # so let's create studies with dates in the future and
        # a negative retention period

        # populate Orthanc with a first "old" future study (CT)
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=8),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=9),
            modality="CT"
        )
        populator.execute()

        ct_study_id = self.oa.studies.get_all_ids()[0]

        # populate Orthanc with a second "old" future study (0T)
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=1,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=8),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=9),
            modality="OT"
        )
        populator.execute()

        studies_ids = self.oa.studies.get_all_ids()

        self.oa.studies.add_label(studies_ids[0], "LABEL6")
        self.oa.studies.add_label(studies_ids[1], "LABEL6")

        cleaner = OrthancCleaner(api_client=self.oa, execution_time=None,
                                 labels_file_path=here / "stimuli/labels.csv")

        cleaner.execute()

        # we would like to check that CT study has been deleted because there is a rule for a short retention period
        # while the OT remains
        self.assertEqual(len(self.oa.studies.get_all_ids()), 1)
        self.assertNotEqual(ct_study_id, self.oa.studies.get_all_ids()[0])

    def test_orthanc_cleaner_with_more_than_100_studies(self):
        self.oa.delete_all_content()

        # populate Orthanc with 120 old studies...
        populator = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=120,
            series_count=1,
            instances_count=1,
            from_study_date=datetime.date.today() + datetime.timedelta(weeks=3),
            to_study_date=datetime.date.today() + datetime.timedelta(weeks=4)
        )
        populator.execute()

        # apply a label to all the studies.
        studies_ids = self.oa.studies.get_all_ids()
        for id in studies_ids:
            self.oa.studies.add_label(id, "LABEL3")

        # then, remove the label for a single study
        self.oa.studies.delete_label(studies_ids[0], "LABEL3")

        # execute cleaner
        cleaner = OrthancCleaner(api_client=self.oa, execution_time=None, labels_file_path=here / "stimuli/labels.csv")
        cleaner.execute()

        # only one single study should be kept
        self.assertEqual(len(self.oa.studies.get_all_ids()), 1)

    def test_folder_importer(self):
        self.oa.delete_all_content()
        with tempfile.TemporaryDirectory() as temp_dir:
            errors_path = os.path.join(temp_dir, 'errors.txt')
            state_path = os.path.join(temp_dir, 'folders.txt')
            importer = OrthancFolderImporter(api_client=self.oa, folder_path=here / "stimuli/MR", errors_path=errors_path, state_path=state_path)
            importer.execute()

            self.assertEqual(4, len(self.oa.instances.get_all_ids()))
            with open(state_path, 'r') as file:
                lines = file.readlines()
                self.assertEqual(3, len(lines))

    def test_folder_importer_with_labels(self):
        self.oa.delete_all_content()
        with tempfile.TemporaryDirectory() as temp_dir:
            errors_path = os.path.join(temp_dir, 'errors.txt')
            state_path = os.path.join(temp_dir, 'folders.txt')
            importer = OrthancFolderImporter(api_client=self.oa, folder_path=here / "stimuli/MR/Brain/1", errors_path=errors_path, state_path=state_path, labels_list=["L1", "L2"])
            importer.execute()

            self.assertEqual(2, len(self.oa.instances.get_all_ids()))
            study_id = self.oa.studies.get_all_ids()
            labels = self.oa.studies.get_labels(study_id[0])
            for label in labels:
                self.assertIn(label, ["L1", "L2"])

    def test_folder_importer_with_bad_files(self):
        self.oa.delete_all_content()
        with tempfile.TemporaryDirectory() as temp_dir:
            errors_path = os.path.join(temp_dir, 'errors.txt')
            state_path = os.path.join(temp_dir, 'folders.txt')
            importer = OrthancFolderImporter(api_client=self.oa, folder_path=here / "stimuli", errors_path=errors_path, state_path=state_path)
            importer.execute()

            self.assertEqual(5, len(self.oa.instances.get_all_ids()))
            with open(errors_path, 'r') as file:
                lines = file.readlines()
                self.assertEqual(3, len(lines))

    def test_folder_importer_with_errors(self):
        self.oa.delete_all_content()

        # let's inhibit orthanc, so that the importer won't be able to upload to it
        with open(here / "docker-setup-replicator/inhibit.lua", 'rb') as f:
            lua_script = f.read()
        self.oa.execute_lua_script(lua_script)

        with tempfile.TemporaryDirectory() as temp_dir:
            errors_path = os.path.join(temp_dir, 'errors.txt')
            state_path = os.path.join(temp_dir, 'folders.txt')
            importer = OrthancFolderImporter(api_client=self.oa, folder_path=here / "stimuli/MR", errors_path=errors_path, state_path=state_path, max_retries=0)
            importer.execute()

            helpers.wait_until(lambda: os.path.exists(errors_path), 2)

            with open(errors_path, 'r') as file:
                lines = file.readlines()
                self.assertEqual(4, len(lines))

        # let's uninhibit Orthanc
        with open(here / "docker-setup-replicator/uninhibit.lua", 'rb') as f:
            lua_script = f.read()
        self.oa.execute_lua_script(lua_script)

    def test_folder_importer_with_restart(self):
        self.oa.delete_all_content()

        # Let's upload the 'Brain' folder
        with tempfile.TemporaryDirectory() as temp_dir:
            errors_path = os.path.join(temp_dir, 'errors.txt')
            state_path = os.path.join(temp_dir, 'folders.txt')
            importer = OrthancFolderImporter(api_client=self.oa, folder_path=here / "stimuli/MR/Brain", errors_path=errors_path, state_path=state_path, max_retries=0)
            importer.execute()

            with open(state_path, 'r') as file:
                lines = file.readlines()
                # 2 folders should have been logged ('1' and '2')
                self.assertEqual(2, len(lines))

            # then, let's execute the importer again, but for the MR folder, only the file at root level should be imported
            # to be sure of that, we will inhibit Orthanc, and count the errors (should be only 1)
            with open(here / "docker-setup-replicator/inhibit.lua", 'rb') as f:
                lua_script = f.read()
            self.oa.execute_lua_script(lua_script)

            importer = OrthancFolderImporter(api_client=self.oa, folder_path=here / "stimuli/MR",
                                             errors_path=errors_path, state_path=state_path, max_retries=0)
            importer.execute()

            helpers.wait_until(lambda: os.path.exists(errors_path), 2)

            with open(errors_path, 'r') as file:
                lines = file.readlines()
                # 1 error should have been logged
                self.assertEqual(1, len(lines))

            # let's uninhibit Orthanc
            with open(here / "docker-setup-replicator/uninhibit.lua", 'rb') as f:
                lua_script = f.read()
            self.oa.execute_lua_script(lua_script)

    def test_orthanc_syncher_as_a_migrator(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        # populate Orthanc A & B with 2 DBs
        populator_a = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=23,
            series_count=3,
            instances_count=4,
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25)
        )
        populator_a.execute()

        populator_b = OrthancTestDbPopulator(
            api_client=self.ob,
            studies_count=23,
            series_count=3,
            instances_count=4,
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25)
        )
        populator_b.execute()

        # transfer a few instances randomly before launching the comparator to make sur it acts correctly on incomplete series ...
        instances_a = self.oa.instances.get_all_ids()
        instances_b = self.ob.instances.get_all_ids()
        self.oa.modalities.send('orthanc-b', [instances_a[0], instances_a[2], instances_a[4]])
        self.ob.modalities.send('orthanc-a', [instances_b[0], instances_b[2], instances_b[4]])

        # run the syncher and make sure that the content of both Orthanc is exactly the same
        syncher = OrthancSyncher(
            api_client_1=self.oa,
            api_client_2=self.ob,
            level='Instance',
            orthanc_queries_batch_size=5
        )
        syncher.execute()

        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))
        self.assertEqual(len(self.oa.instances.get_all_ids()), 552)

    def test_orthanc_syncher_with_recovery(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()

        # populate Orthanc A
        populator_a = OrthancTestDbPopulator(
            api_client=self.oa,
            studies_count=15,
            series_count=3,
            instances_count=2,
            from_study_date=datetime.date(2022, 4, 19),
            to_study_date=datetime.date(2022, 4, 25)
        )
        populator_a.execute()
        with tempfile.TemporaryDirectory() as temp_dir:
            persist_status_path = os.path.join(temp_dir, 'status.txt')

            # run the syncher and make sure that the content of both Orthanc is the same
            syncher = OrthancSyncher(
                api_client_1=self.oa,
                api_client_2=self.ob,
                level='Instance',
                persist_status_path=persist_status_path,
                orthanc_queries_batch_size=5
            )
            syncher.execute()

            self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

            # add some new images to the Orthanc A
            populator_a = OrthancTestDbPopulator(
                api_client=self.oa,
                studies_count=3,
                series_count=3,
                instances_count=2,
                from_study_date=datetime.date(2025, 4, 19),
                to_study_date=datetime.date(2025, 10, 25)
            )
            populator_a.execute()

            syncher.execute()
            self.assertEqual(len(self.oa.instances.get_all_ids()), 108)



if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main()

