import unittest
from types import SimpleNamespace
from unittest.mock import patch

from orthanc_api_client import ChangeType

from orthanc_tools import OrthancForwarder


class FakeStudies:
    def __init__(self, is_stable):
        self.is_stable = is_stable

    def get(self, study_id):
        return SimpleNamespace(is_stable=self.is_stable)


class FakeApiClient:
    def __init__(self, is_stable):
        self.studies = FakeStudies(is_stable=is_stable)


class TestOrthancForwarderStability(unittest.TestCase):
    def test_stable_study_trigger_leaves_unstable_study_untouched(self):
        api_client = FakeApiClient(is_stable=False)
        forwarder = OrthancForwarder(
            source=api_client,
            destinations=[],
            trigger=ChangeType.STABLE_STUDY,
        )

        with patch("orthanc_tools.orthanc_forwarder.InstancesSet.from_study") as from_study:
            with patch.object(forwarder, "handle_instances_set") as handle_instances_set:
                forwarder._handle_study("study-id", api_client)

        from_study.assert_not_called()
        handle_instances_set.assert_not_called()

    def test_stable_study_trigger_handles_stable_study(self):
        api_client = FakeApiClient(is_stable=True)
        instances_set = object()
        forwarder = OrthancForwarder(
            source=api_client,
            destinations=[],
            trigger=ChangeType.STABLE_STUDY,
        )

        with patch("orthanc_tools.orthanc_forwarder.InstancesSet.from_study", return_value=instances_set) as from_study:
            with patch.object(forwarder, "handle_instances_set") as handle_instances_set:
                forwarder._handle_study("study-id", api_client)

        from_study.assert_called_once_with(api_client=api_client, study_id="study-id")
        handle_instances_set.assert_called_once_with(instances_set)


if __name__ == "__main__":
    unittest.main()
