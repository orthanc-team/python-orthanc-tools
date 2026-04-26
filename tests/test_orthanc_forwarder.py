import os
import tempfile
import unittest
from unittest import mock

from orthanc_api_client import exceptions

from orthanc_tools.orthanc_cloner import OrthancCloner
from orthanc_tools.orthanc_forwarder import (
    OrthancForwarder,
    ForwarderDestination,
    ForwarderInstancesSetStatus,
    ForwarderMode,
    StudyDescriptionMatchType,
    build_forwarder_destination,
    parse_forwarder_destinations,
    split_cli_destination_entries,
    split_destination_entries,
)
from orthanc_tools.orthanc_folder_importer import OrthancFolderImporter


class TestOrthancForwarderConfiguration(unittest.TestCase):

    def test_build_destination_without_filter(self):
        destination = build_forwarder_destination("orthanc-b:dicom", ForwarderMode.TRANSFER)

        self.assertEqual("orthanc-b", destination.destination)
        self.assertEqual(ForwarderMode.DICOM, destination.forwarder_mode)
        self.assertIsNone(destination.study_description_match_type)
        self.assertIsNone(destination.study_description_pattern)

    def test_build_destination_with_substring_filter(self):
        destination = build_forwarder_destination("ai:dicom:substring:brain", ForwarderMode.TRANSFER)

        self.assertEqual("ai", destination.destination)
        self.assertEqual(ForwarderMode.DICOM, destination.forwarder_mode)
        self.assertEqual(StudyDescriptionMatchType.SUBSTRING, destination.study_description_match_type)
        self.assertEqual("brain", destination.study_description_pattern)
        self.assertTrue(destination.matches_study_description("Brain MRI"))
        self.assertFalse(destination.matches_study_description("CT Abdomen"))

    def test_build_destination_with_regex_filter(self):
        destination = build_forwarder_destination("ai:dicom:regex:^brain:mr$", ForwarderMode.TRANSFER)

        self.assertEqual("ai", destination.destination)
        self.assertEqual(ForwarderMode.DICOM, destination.forwarder_mode)
        self.assertEqual(StudyDescriptionMatchType.REGEX, destination.study_description_match_type)
        self.assertEqual("^brain:mr$", destination.study_description_pattern)
        self.assertTrue(destination.matches_study_description("Brain:MR"))
        self.assertFalse(destination.matches_study_description("Spine:MR"))

    def test_build_destination_uses_default_mode_when_left_blank(self):
        destination = build_forwarder_destination("ai::substring:brain", ForwarderMode.TRANSFER)

        self.assertEqual(ForwarderMode.TRANSFER, destination.forwarder_mode)
        self.assertEqual(StudyDescriptionMatchType.SUBSTRING, destination.study_description_match_type)

    def test_build_destination_rejects_invalid_match_type(self):
        with self.assertRaisesRegex(ValueError, "Invalid StudyDescription match type"):
            build_forwarder_destination("ai:dicom:exact:brain", ForwarderMode.TRANSFER)

    def test_build_destination_rejects_blank_pattern(self):
        with self.assertRaisesRegex(ValueError, "pattern is missing"):
            build_forwarder_destination("ai:dicom:substring:", ForwarderMode.TRANSFER)

    def test_build_destination_rejects_invalid_regex(self):
        with self.assertRaisesRegex(ValueError, "Invalid StudyDescription regex"):
            build_forwarder_destination("ai:dicom:regex:[", ForwarderMode.TRANSFER)

    def test_parse_multiple_destinations(self):
        destinations = parse_forwarder_destinations(
            ["orthanc-b:dicom", "ai::substring:brain"],
            ForwarderMode.TRANSFER
        )

        self.assertEqual(2, len(destinations))
        self.assertEqual(ForwarderMode.DICOM, destinations[0].forwarder_mode)
        self.assertEqual(ForwarderMode.TRANSFER, destinations[1].forwarder_mode)

    def test_retry_key_includes_filter(self):
        unfiltered = ForwarderDestination(destination="ai", forwarder_mode=ForwarderMode.DICOM)
        filtered = ForwarderDestination(
            destination="ai",
            forwarder_mode=ForwarderMode.DICOM,
            study_description_match_type=StudyDescriptionMatchType.SUBSTRING,
            study_description_pattern="brain"
        )

        self.assertNotEqual(unfiltered.retry_key, filtered.retry_key)

    def test_split_destination_entries_preserves_quoted_commas(self):
        destinations = split_destination_entries('orthanc-b:dicom,"ai:dicom:substring:CT, ABDOMEN"')

        self.assertEqual(
            ["orthanc-b:dicom", "ai:dicom:substring:CT, ABDOMEN"],
            destinations
        )

    def test_split_destination_entries_preserves_backslashes_in_regex_patterns(self):
        destinations = split_destination_entries(r'ai:dicom:regex:^CT\d+$')

        self.assertEqual([r'ai:dicom:regex:^CT\d+$'], destinations)

    def test_split_cli_destination_entries_splits_each_argument(self):
        destinations = split_cli_destination_entries([
            'peer-a:peering,modality-b:dicom',
            '"ai:dicom:substring:CT, ABDOMEN"'
        ])

        self.assertEqual(
            ["peer-a:peering", "modality-b:dicom", "ai:dicom:substring:CT, ABDOMEN"],
            destinations
        )

    def test_parse_destination_with_comma_in_pattern(self):
        destinations = parse_forwarder_destinations(
            ["ai:dicom:substring:CT, ABDOMEN"],
            ForwarderMode.TRANSFER
        )

        self.assertEqual(1, len(destinations))
        self.assertEqual("CT, ABDOMEN", destinations[0].study_description_pattern)


class FakeInstancesSet:
    def __init__(self):
        self.id = "study-1"
        self.instances_ids = ["instance-1"]
        self.series_ids = []
        self.deleted = False
        self.filtered = None
        self.filter_calls = 0
        self.process_calls = 0

    def delete(self):
        self.deleted = True

    def filter_instances(self, instance_filter):
        self.filter_calls += 1
        self.filtered = FakeInstancesSet()
        self.filtered.id = f"{self.id}-filtered"
        self.filtered.instances_ids = []

        for instance_id in self.instances_ids:
            if not instance_filter(mock.sentinel.api_client, instance_id):
                self.filtered.instances_ids.append(instance_id)

        return self.filtered

    def process_instances(self, processor):
        self.process_calls += 1
        for instance_id in self.instances_ids:
            processor(mock.sentinel.api_client, instance_id)


class TestOrthancForwarderFilteringBehavior(unittest.TestCase):

    def test_forward_does_not_lookup_study_description_when_no_destination_is_filtered(self):
        forwarder = OrthancForwarder(
            source=mock.MagicMock(),
            destinations=[ForwarderDestination(destination="orthanc-b", forwarder_mode=ForwarderMode.DICOM)]
        )
        instances_set = FakeInstancesSet()

        with mock.patch.object(forwarder, "_get_study_description", side_effect=AssertionError("unexpected lookup")):
            with mock.patch.object(forwarder, "_forward_to_destination") as forward_to_destination:
                sent_to_destinations, eligible_destinations = forwarder.forward(instances_set, [])

        self.assertEqual(["dicom:orthanc-b::"], sent_to_destinations)
        self.assertEqual(["dicom:orthanc-b::"], eligible_destinations)
        forward_to_destination.assert_called_once_with(instances_set=instances_set, destination=forwarder._destinations[0])

    def test_filtered_only_non_matching_study_runs_hooks_before_terminal_skip(self):
        instance_filter = mock.Mock(return_value=False)
        instance_processor = mock.Mock()
        forwarder = OrthancForwarder(
            source=mock.MagicMock(),
            destinations=[
                ForwarderDestination(
                    destination="ai",
                    forwarder_mode=ForwarderMode.DICOM,
                    study_description_match_type=StudyDescriptionMatchType.SUBSTRING,
                    study_description_pattern="brain"
                )
            ],
            instance_filter=instance_filter,
            instance_processor=instance_processor
        )
        instances_set = FakeInstancesSet()

        with mock.patch.object(forwarder, "_get_study_description", return_value="abdomen") as get_study_description:
            with mock.patch.object(forwarder, "_forward_to_destination") as forward_to_destination:
                forwarder.handle_instances_set(instances_set)
                forwarder.handle_instances_set(instances_set)

        self.assertFalse(instances_set.deleted)
        self.assertTrue(forwarder._status[instances_set.id].processed)
        self.assertEqual([], forwarder._status[instances_set.id].sent_to_destinations)
        self.assertEqual([], forwarder._status[instances_set.id].last_eligible_destinations)
        self.assertEqual(0, forwarder._status[instances_set.id].retry_count)
        self.assertIsNone(forwarder._status[instances_set.id].next_retry)
        self.assertTrue(forwarder._status[instances_set.id].terminal)
        self.assertEqual(1, instances_set.filter_calls)
        self.assertTrue(instances_set.filtered.deleted)
        self.assertEqual(1, instances_set.process_calls)
        instance_filter.assert_called_once_with(mock.sentinel.api_client, "instance-1")
        instance_processor.assert_called_once_with(mock.sentinel.api_client, "instance-1")
        get_study_description.assert_called_once_with(instances_set)
        forward_to_destination.assert_not_called()

    def test_already_sent_study_is_deleted_when_remaining_filtered_destinations_do_not_match(self):
        forwarder = OrthancForwarder(
            source=mock.MagicMock(),
            destinations=[
                ForwarderDestination(destination="orthanc-b", forwarder_mode=ForwarderMode.DICOM),
                ForwarderDestination(
                    destination="ai",
                    forwarder_mode=ForwarderMode.DICOM,
                    study_description_match_type=StudyDescriptionMatchType.SUBSTRING,
                    study_description_pattern="brain"
                )
            ]
        )
        instances_set = FakeInstancesSet()
        forwarder._status[instances_set.id] = ForwarderInstancesSetStatus()
        forwarder._status[instances_set.id].sent_to_destinations = ["dicom:orthanc-b::"]

        with mock.patch.object(forwarder, "_get_study_description", return_value="abdomen") as get_study_description:
            with mock.patch.object(forwarder, "_forward_to_destination") as forward_to_destination:
                forwarder.handle_instances_set(instances_set)

        self.assertTrue(instances_set.deleted)
        self.assertEqual(0, instances_set.process_calls)
        self.assertNotIn(instances_set.id, forwarder._status)
        get_study_description.assert_called_once_with(instances_set)
        forward_to_destination.assert_not_called()

    def test_filter_metadata_read_failure_keeps_filtered_destination_retryable(self):
        forwarder = OrthancForwarder(
            source=mock.MagicMock(),
            destinations=[
                ForwarderDestination(destination="orthanc-b", forwarder_mode=ForwarderMode.DICOM),
                ForwarderDestination(
                    destination="ai",
                    forwarder_mode=ForwarderMode.DICOM,
                    study_description_match_type=StudyDescriptionMatchType.SUBSTRING,
                    study_description_pattern="brain"
                )
            ],
            polling_interval_in_seconds=0
        )
        instances_set = FakeInstancesSet()

        with mock.patch.object(forwarder, "_get_study_description", side_effect=RuntimeError("study lookup failed")):
            with mock.patch.object(forwarder, "_forward_to_destination") as forward_to_destination:
                forwarder.handle_instances_set(instances_set)

        self.assertFalse(instances_set.deleted)
        self.assertEqual(["dicom:orthanc-b::"], forwarder._status[instances_set.id].sent_to_destinations)
        self.assertEqual(
            ["dicom:orthanc-b::", "dicom:ai:substring:brain"],
            forwarder._status[instances_set.id].last_eligible_destinations
        )
        self.assertEqual(1, forwarder._status[instances_set.id].retry_count)
        self.assertIsNotNone(forwarder._status[instances_set.id].next_retry)
        forward_to_destination.assert_called_once_with(instances_set=instances_set, destination=forwarder._destinations[0])

class TestOrthancFolderImporterConnectivity(unittest.TestCase):

    def test_permanent_unreachable_orthanc_logs_error_instead_of_waiting_forever(self):
        api_client = mock.MagicMock()
        api_client.is_alive.return_value = False
        api_client.upload.return_value = []

        with tempfile.TemporaryDirectory() as temp_dir:
            dicom_path = os.path.join(temp_dir, "test.dcm")
            errors_path = os.path.join(temp_dir, "errors.txt")

            with open(dicom_path, "wb") as dicom_file:
                dicom_file.write(b"DICM")

            importer = OrthancFolderImporter(
                api_client=api_client,
                folder_path=temp_dir,
                errors_path=errors_path,
                state_path=None,
                max_retries=0
            )

            with mock.patch("orthanc_tools.orthanc_folder_importer.ORTHANC_READY_MAX_CHECKS", 1):
                with mock.patch("orthanc_tools.orthanc_folder_importer.ORTHANC_READY_RECHECK_DELAY_SECONDS", 0):
                    with mock.patch("orthanc_tools.orthanc_folder_importer.time.sleep"):
                        importer.upload_and_label(dicom_path)

            with open(errors_path, "rt") as errors_file:
                self.assertEqual([dicom_path + "\n"], errors_file.readlines())


class TestOrthancClonerTimeouts(unittest.TestCase):

    def test_download_timeout_is_enforced_when_client_accepts_timeout(self):
        cloner = object.__new__(OrthancCloner)
        cloner._transfer_timeout = 0.01
        api_client = mock.MagicMock()
        api_client.get_binary.side_effect = TimeoutError("download timed out")

        with self.assertRaises(TimeoutError):
            cloner._download_with_timeout(api_client, "instance-1")

        api_client.get_binary.assert_called_once_with("instances/instance-1/file", timeout=0.01)

    def test_download_falls_back_when_client_does_not_accept_timeout(self):
        cloner = object.__new__(OrthancCloner)
        cloner._transfer_timeout = 0.01
        api_client = mock.MagicMock()
        api_client.get_binary.side_effect = [
            TypeError("get_binary() got an unexpected keyword argument 'timeout'"),
            b"dicom",
        ]

        self.assertEqual(b"dicom", cloner._download_with_timeout(api_client, "instance-1"))

        self.assertEqual(
            [
                mock.call("instances/instance-1/file", timeout=0.01),
                mock.call("instances/instance-1/file"),
            ],
            api_client.get_binary.call_args_list
        )

    def test_upload_timeout_is_enforced_when_client_accepts_timeout(self):
        cloner = object.__new__(OrthancCloner)
        cloner._transfer_timeout = 0.01
        cloner._destination = mock.MagicMock()
        cloner._destination.post.side_effect = TimeoutError("upload timed out")

        with self.assertRaises(TimeoutError):
            cloner._upload_with_timeout(b"dicom")

        cloner._destination.post.assert_called_once_with('instances', data=b"dicom", timeout=0.01)

    def test_upload_falls_back_when_client_does_not_accept_timeout(self):
        cloner = object.__new__(OrthancCloner)
        cloner._transfer_timeout = 0.01
        cloner._destination = mock.MagicMock()
        response = mock.MagicMock()
        response.json.return_value = {'ID': 'instance-1'}
        cloner._destination.post.side_effect = [
            TypeError("post() got an unexpected keyword argument 'timeout'"),
            response,
        ]

        self.assertEqual(["instance-1"], cloner._upload_with_timeout(b"dicom"))

        self.assertEqual(
            [
                mock.call('instances', data=b"dicom", timeout=0.01),
                mock.call('instances', data=b"dicom"),
            ],
            cloner._destination.post.call_args_list
        )
