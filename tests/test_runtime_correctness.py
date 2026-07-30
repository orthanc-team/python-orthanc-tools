import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orthanc_tools.helpers.environment import get_env_bool
from orthanc_tools.orthanc_syncher import OrthancSyncher
from orthanc_tools.orthanc_uploader import OrthancUploader
from orthanc_tools.orthanc_warmer import OrthancWarmer


class TestBooleanEnvironmentVariables(unittest.TestCase):
    def test_false_string_is_false(self):
        with mock.patch.dict(os.environ, {"FEATURE_ENABLED": "false"}):
            self.assertFalse(get_env_bool("FEATURE_ENABLED", True))

    def test_true_values_are_case_insensitive(self):
        with mock.patch.dict(os.environ, {"FEATURE_ENABLED": "YeS"}):
            self.assertTrue(get_env_bool("FEATURE_ENABLED"))

    def test_missing_value_uses_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(get_env_bool("FEATURE_ENABLED", True))

    def test_invalid_value_is_rejected(self):
        with mock.patch.dict(os.environ, {"FEATURE_ENABLED": "sometimes"}):
            with self.assertRaisesRegex(ValueError, "FEATURE_ENABLED"):
                get_env_bool("FEATURE_ENABLED")


class TestInjectedApiClients(unittest.TestCase):
    def test_uploader_uses_injected_client(self):
        api_client = mock.MagicMock()
        api_client.upload_file.return_value = ["instance-id"]
        api_client.instances.get_parent_study_id.return_value = "study-id"

        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "instance.dcm").touch()
            uploader = OrthancUploader(api_client=api_client, path=temp_dir)

            uploader.upload_folder_and_label(temp_dir, ["reviewed"])

        api_client.upload_file.assert_called_once()
        api_client.instances.get_parent_study_id.assert_called_once_with("instance-id")
        api_client.studies.add_labels.assert_called_once_with(
            orthanc_id="study-id",
            labels=["reviewed"],
        )

    def test_warmer_uses_injected_client(self):
        api_client = mock.MagicMock()
        warmer = OrthancWarmer(api_client=api_client, interval=30)

        warmer.find()

        api_client.studies.find.assert_called_once_with(
            query={"StudyDate": "19500101"}
        )
        self.assertEqual(0, warmer._errors_counter)


class TestOrthancSyncherSafety(unittest.TestCase):
    def _syncher(self, **kwargs):
        return OrthancSyncher(
            api_client_1=mock.MagicMock(),
            api_client_2=mock.MagicMock(),
            **kwargs,
        )

    def test_empty_source_preserves_last_update_limit(self):
        last_update_limit = datetime.datetime(2026, 7, 30, 12, 0, 0)
        syncher = self._syncher()
        syncher.get_studies = mock.Mock(return_value=[])

        result = syncher.synch(
            orthanc_source=mock.sentinel.source,
            orthanc_destination=mock.sentinel.destination,
            last_update_limit=last_update_limit,
        )

        self.assertEqual(last_update_limit, result)

    def test_scheduler_is_checked_before_querying_a_batch(self):
        scheduler = mock.Mock()
        syncher = self._syncher(scheduler=scheduler)
        syncher.get_studies = mock.Mock(return_value=[])

        syncher.synch(
            orthanc_source=mock.sentinel.source,
            orthanc_destination=mock.sentinel.destination,
            last_update_limit=datetime.datetime(2026, 7, 30, 12, 0, 0),
        )

        scheduler.wait_right_time_to_run.assert_called_once_with()

    def test_invalid_status_file_is_reinitialized_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status_path = os.path.join(temp_dir, "status.txt")
            Path(status_path).write_text("truncated\n", encoding="utf-8")

            syncher = self._syncher(persist_status_path=status_path)

            self.assertEqual(syncher._initial_last_update(), syncher._run_till_last_update_1)
            self.assertEqual(syncher._initial_last_update(), syncher._run_till_last_update_2)
            self.assertEqual(
                ["1950-01-01 01:01:01", "1950-01-01 01:01:01"],
                Path(status_path).read_text(encoding="utf-8").splitlines(),
            )
            self.assertEqual(["status.txt"], os.listdir(temp_dir))

    def test_transfer_failure_raises_instead_of_exiting_process(self):
        source = mock.MagicMock()
        source.instances.get_file.side_effect = RuntimeError("offline")
        source.instances.get_parent_study_id.return_value = "study-id"
        syncher = self._syncher()

        with mock.patch("orthanc_tools.orthanc_syncher.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "6 attempts"):
                syncher.transfer_instances(
                    orthanc_source=source,
                    orthanc_destination=mock.MagicMock(),
                    instances_ids=["instance-id"],
                )

        self.assertEqual(6, source.instances.get_file.call_count)


if __name__ == "__main__":
    unittest.main()
