import subprocess
import time

from orthanc_api_client import OrthancApiClient, helpers
import pathlib
import logging
import unittest
import json
import requests

from orthanc_tools import LabelModifier

here = pathlib.Path(__file__).parent.resolve()

logger = logging.getLogger('orthanc_tools')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class TestLabelModifier(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"docker-setup-auth")
        subprocess.run(["docker", "compose", "up", "-d"], cwd=here/"docker-setup-auth")

        cls.oa = OrthancApiClient('http://localhost:10042', user='test', pwd='test')
        cls.oa.wait_started()

        cls.auth_url = "http://localhost:18000"
        cls.auth_user = "test"
        cls.auth_pwd = "test"

        # waiting for the auth service to be ready to accept queries
        cls.wait_auth_service_started(url=cls.auth_url, auth=(cls.auth_user, cls.auth_pwd))

        cls.permissions_old = {
          "roles": {
            "admin-role": {
              "authorized-labels": [
                "TEST",
                "OLD2"
              ],
              "permissions": [
                "all",
                "admin-permissions"
              ]
            },
            "doctor-role": {
              "authorized-labels": [
                "OLD",
                "TEST",
                "OLD2"
              ],
              "permissions": [
                "view",
                "download",
                "share",
                "send"
              ]
            },
            "external-role": {
              "authorized-labels": [
                "OLD"
              ],
              "permissions": [
                "view",
                "download"
              ]
            }
          },
          "available-labels": [
            "TEST",
            "OLD2",
            "OLD"
          ]
        }

        cls.permissions_new = {
          "roles": {
            "admin-role": {
              "authorized-labels": [
                "TEST",
                "OLD2"
              ],
              "permissions": [
                "all",
                "admin-permissions"
              ]
            },
            "doctor-role": {
              "authorized-labels": [
                "NEW",
                "TEST",
                "OLD2"
              ],
              "permissions": [
                "view",
                "download",
                "share",
                "send"
              ]
            },
            "external-role": {
              "authorized-labels": [
                "NEW"
              ],
              "permissions": [
                "view",
                "download"
              ]
            }
          },
          "available-labels": [
            "TEST",
            "OLD2",
            "NEW"
          ]
        }

        cls.permissions_new2 = {
          "roles": {
            "admin-role": {
              "authorized-labels": [
                "TEST",
                "OLD2"
              ],
              "permissions": [
                "all",
                "admin-permissions"
              ]
            },
            "doctor-role": {
              "authorized-labels": [
                "TEST",
                "OLD2"
              ],
              "permissions": [
                "view",
                "download",
                "share",
                "send"
              ]
            },
            "external-role": {
              "authorized-labels": [
                "OLD2"
              ],
              "permissions": [
                "view",
                "download"
              ]
            }
          },
          "available-labels": [
            "TEST",
            "OLD2"
          ]
        }

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"docker-setup-auth")

    @classmethod
    def wait_auth_service_started(cls, url, auth):
        ready = False
        while not ready:
            try:
                response = requests.get(url=url + "/settings/roles", auth=auth)
                if response.status_code == 200:
                    ready = True
            except Exception as ex:
                time.sleep(1)

    def sorting(self, item):
        if isinstance(item, dict):
            return sorted((key, self.sorting(values)) for key, values in item.items())
        if isinstance(item, list):
            return sorted(self.sorting(x) for x in item)
        else:
            return item

    def test_apply_new_label(self):

        # clean up
        self.oa.delete_all_content()

        # upload an instance
        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        old_label = "OLD"
        new_label = "NEW"

        # apply label on this study
        study_id = self.oa.studies.get_all_ids()[0]
        self.oa.studies.add_label(study_id, old_label)

        modifier = LabelModifier(api_client=self.oa, auth_service_url=self.auth_url, auth_service_login=self.auth_user, auth_service_password=self.auth_pwd)

        modifier.apply_new_label(new_label=new_label, old_label=old_label)

        self.assertEqual(len(self.oa.studies.find(query={'PatientID': '*'}, labels=[new_label])), 1)
        self.assertEqual(len(self.oa.studies.find(query={'PatientID': '*'}, labels=[old_label])), 0)


    def test_modify_permissions(self):

        # reset permissions.json file to original values
        with open(here / "docker-setup-auth/permissions.json", 'w') as f:
            f.write(json.dumps(self.permissions_old))

        subprocess.run(["docker", "compose", "restart", "orthanc-auth-service"], cwd=here / "docker-setup-auth")

        # waiting for the auth service to be ready to accept queries
        self.wait_auth_service_started(self.auth_url, (self.auth_user, self.auth_pwd))

        modifier = LabelModifier(api_client=self.oa, auth_service_url=self.auth_url, auth_service_login=self.auth_user, auth_service_password=self.auth_pwd)

        old_label = "OLD"
        new_label = "NEW"

        modifier.modify_permissions(old_label=old_label, new_label=new_label)
        modifier.add_label_to_available_list(label_to_add=new_label)
        modifier.remove_label_from_available_list(label_to_remove=old_label)

        current_permissions = modifier.get_roles()
        self.assertEqual(self.sorting(current_permissions), self.sorting(self.permissions_new))

    def test_modify_permissions_with_existing_label(self):
        '''
        To check that a label is not twice in a list
        '''

        # reset permissions.json file to original values
        with open(here / "docker-setup-auth/permissions.json", 'w') as f:
            f.write(json.dumps(self.permissions_old))

        # restart auth service to take file in account
        subprocess.run(["docker", "compose", "restart", "orthanc-auth-service"], cwd=here / "docker-setup-auth")

        # waiting for the auth service to be ready to accept queries
        self.wait_auth_service_started(self.auth_url, (self.auth_user, self.auth_pwd))

        modifier = LabelModifier(api_client=self.oa, auth_service_url=self.auth_url, auth_service_login=self.auth_user, auth_service_password=self.auth_pwd)

        old_label = "OLD"
        new_label = "OLD2"

        modifier.modify_permissions(old_label=old_label, new_label=new_label)
        modifier.add_label_to_available_list(label_to_add=new_label)
        modifier.remove_label_from_available_list(label_to_remove=old_label)

        current_permissions = modifier.get_roles()
        self.assertEqual(self.sorting(current_permissions), self.sorting(self.permissions_new2))

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main()

