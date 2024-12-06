import json
import pprint

import inquirer
import logging
import argparse
from orthanc_api_client import OrthancApiClient
import sys
import requests
logger = logging.getLogger(__name__)

'''
WARNING
-------
This script is interactive!
So, run it from the console and follow instructions...

PURPOSE
-------
This script allows to handle the fix of a typo in a label name.

HOW IT WORKS
------------
    ask for the creds

    show the list of labels and ask for the one to change

    ask for the new label value

    add the new label to the list of available labels (if this list is not empty)

    apply new label to all the studies from existing one

    remove original label from all the studies from the new one

    handle permissions
    
    remove the old label from the list of available labels (if this list is not empty)

HOW TO USE IT
-------------
- get the url and creds for both Orthanc and Auth-service
- Run it thanks to:
`python3 label_modifier.py --orthanc_url=http://localhost/orthanc-api/ --orthanc_user=demo --auth_url=http://localhost/auth-service --auth_user=demo`
- Note that password will be prompted by the script itself
'''

class LabelModifier:
    def __init__(self,
                 api_client: OrthancApiClient,
                 auth_service_url: str,
                 auth_service_login: str,
                 auth_service_password: str
                 ):
        self._api_client = api_client
        self._auth_service_url = auth_service_url
        self._auth_service_login = auth_service_login
        self._auth_service_password = auth_service_password

        self._auth_service_roles_url = self._auth_service_url + "/settings/roles"
        self._auth_service_auth = (self._auth_service_login, self._auth_service_password)


    def apply_new_label(self, new_label: str, old_label: str):

        # Here is a loop because the find will be limited to LimitFindResults value
        while True:
            # find all the studies with the old label
            studies = self._api_client.studies.find(
                query={},
                labels=[old_label]
            )
            if len(studies) == 0:
                return

            # add the new label and then delete the old one
            for study in studies:
                self._api_client.studies.add_label(study.orthanc_id, new_label)
                self._api_client.studies.delete_label(study.orthanc_id, old_label)

    def get_roles(self):

        # get the roles/perm
        response = requests.get(self._auth_service_roles_url, auth=self._auth_service_auth)

        # Check if request was successful
        if response.status_code == 200:
            # get json (as a string)
            return response.json()
        else:
            logger.error("Error getting permissions:", response.status_code)
            sys.exit(1)

    def modify_permissions(self, new_label: str, old_label: str):

        content_as_json = self.get_roles()

        # replace old label by new one
        modified_content = self.update_dict_values(content_as_json, "authorized-labels", old_label, new_label)

        # push the modifications
        response = requests.put(
            url=self._auth_service_roles_url,
            json=modified_content,
            auth=self._auth_service_auth)

        if response.status_code != 200:
            logger.error("Error setting permissions:", response.status_code)
            sys.exit(1)

    def add_label_to_available_list(self, label_to_add: str):
        content_as_json = self.get_roles()

        # get available-labels
        available_labels = content_as_json["available-labels"]

        # if there is no restriction on labels, let's forget it
        if len(available_labels) == 0:
            return

        # let's add the new label to the list (without duplicate)
        temp_list = content_as_json["available-labels"]
        temp_list.append(label_to_add)
        content_as_json["available-labels"] = list(dict.fromkeys(temp_list))

        # push the modifications
        response = requests.put(
            url=self._auth_service_roles_url,
            json=content_as_json,
            auth=self._auth_service_auth)

        if response.status_code != 200:
            logger.error("Error setting permissions:", response.status_code)
            sys.exit(1)

    def remove_label_from_available_list(self, label_to_remove: str):
        content_as_json = self.get_roles()

        # get available-labels
        available_labels = content_as_json["available-labels"]

        # if there is no restriction on labels, let's forget it
        if len(available_labels) == 0:
            return

        # let's remove the old label from the list
        content_as_json["available-labels"].remove(label_to_remove)

        # push the modifications
        response = requests.put(
            url=self._auth_service_roles_url,
            json=content_as_json,
            auth=self._auth_service_auth)

        if response.status_code != 200:
            logger.error("Error setting permissions:", response.status_code)
            sys.exit(1)

    def update_dict_values(self, data, target_key, old_value, new_value):
        """
        Searches for a specific key in a nested dictionary, updates the target value in arrays if the key is found.

        :param data: The dictionary to search.
        :param target_key: The key to find in the dictionary.
        :param old_value: The value to replace in the arrays.
        :param new_value: The new value to use for replacement.
        :return: Updated dictionary.
        """
        if isinstance(data, dict):
            for key, value in data.items():
                if key == target_key and isinstance(value, list):
                    # Replace old_value with new_value in the array
                    updated_list = [new_value if item == old_value else item for item in value]
                    data[key] = list(dict.fromkeys(updated_list))  # Remove duplicates
                elif isinstance(value, (dict, list)):
                    # Recursively process nested dictionaries and lists
                    self.update_dict_values(value, target_key, old_value, new_value)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    # Recursively process lists of dictionaries or nested lists
                    self.update_dict_values(item, target_key, old_value, new_value)
        return data

    def execute(self):

        # let's get the existing labels
        labels_list = self._api_client.get_all_labels()
        label_to_modify = None

        # let the user choose the label to modify
        if len(labels_list)>0:
            questions_labels = [
                inquirer.List(
                    "orthanc_labels_chosen_list",
                    message="Choose the label to modify",
                    choices=labels_list,
                )
            ]

            answers = inquirer.prompt(questions_labels)
            label_to_modify = answers['orthanc_labels_chosen_list']
        else:
            logger.error(f"No labels found, exiting...")
            sys.exit(1)

        # let the user choose the new value for the label to modify
        questions_labels = [
            inquirer.Text(
                "new_label_value",
                message="Write the new value for the label",
            )
        ]

        answers = inquirer.prompt(questions_labels)
        label_new_value = answers['new_label_value']

        print("-----------------------------------------------------------------------------------")
        print(f"This change will be applied:\r\n   \"{label_to_modify}\" will become \"{label_new_value}\"")
        questions_continue = [
            inquirer.Confirm("continue", message="Do you confirm?", default=True)
        ]

        answers = inquirer.prompt(questions_continue)
        if answers['continue'] == False:
            print("Aborted!")
            exit(-1)

        logger.info(f"Starting label modification...")

        # add new label into the available-labels list (if not empty)
        self.add_label_to_available_list(label_to_add=label_new_value)

        self.apply_new_label(new_label=label_new_value, old_label=label_to_modify)
        logger.info(f"Applied new label.")

        self.modify_permissions(new_label=label_new_value, old_label=label_to_modify)
        logger.info(f"Modified permissions.")

        # remove old label from the available-labels list
        self.remove_label_from_available_list(label_to_remove=label_to_modify)

        logger.info("End of label modification!")


if __name__ == '__main__':
    level = logging.INFO

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="Ask user to choose a label to modify.")
    parser.add_argument('--orthanc_url', help="The url of the Orthanc to modifiy the label to.", default="http://localhost:8042")
    parser.add_argument('--orthanc_user', help="The user of the Orthanc to modifiy the label to.", default="demo")
    parser.add_argument('--orthanc_password', help="The password of the Orthanc to modifiy the label to.", default=None)

    parser.add_argument('--auth_url', help="The root url of the auth service to modifiy the permissions to.", default="http://localhost/auth-service/")
    parser.add_argument('--auth_user', help="The user of the auth service to modifiy the permissions to.", default="demo")
    parser.add_argument('--auth_password', help="The password of the auth service to modifiy the permissions to.", default=None)

    args = parser.parse_args()

    orthanc_url = args.orthanc_url
    orthanc_user = args.orthanc_user
    orthanc_password = args.orthanc_password

    auth_url = args.auth_url
    auth_user = args.auth_user
    auth_password = args.auth_password

    # password should always be avoided as an argument of the command, so that it is not in the terminal history
    if orthanc_password is None:
        questions = [
            inquirer.Text('orthanc_password', message="Please enter Orthanc password")
        ]
        answers = inquirer.prompt(questions)
        orthanc_password = answers["orthanc_password"]

    if auth_password is None:
        questions = [
            inquirer.Text('auth_password', message="Please enter Auth-Service password")
        ]
        answers = inquirer.prompt(questions)
        auth_password = answers["auth_password"]

    orthanc_client=OrthancApiClient(orthanc_url, user=orthanc_user, pwd=orthanc_password)

    if auth_url[-1] == "/":
        auth_url = auth_url[:-1]
    modifier = LabelModifier(api_client=orthanc_client, auth_service_url=auth_url, auth_service_login=auth_user, auth_service_password=auth_password)

    # will crash if password is wrong
    modifier.get_roles()

    modifier.execute()
