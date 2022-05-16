import queue
import threading
import time
import os
import logging
import argparse
import datetime
import random
import pydicom
import uuid

from orthanc_api_client import OrthancApiClient
from orthanc_api_client import helpers
logger = logging.getLogger('orthanc_tools')


male_first_names = ['Adam', 'Adrian', 'Alan', 'Alexander', 'Andrew', 'Anthony', 'Austin', 'Benjamin', 'Blake', 'Boris', 'Brandon', 'Brian', 'Cameron', 'Carl', 'Charles', 'Christian', 'Christopher',
    'Colin', 'Connor', 'Dan', 'David', 'Dominic', 'Dylan', 'Edward', 'Eric', 'Evan', 'Frank', 'Gavin', 'Gordon', 'Harry', 'Ian', 'Isaac', 'Jack', 'Jacob', 'Jake', 'James', 'Jason',
    'Joe', 'John', 'Jonathan', 'Joseph', 'Joshua', 'Julian', 'Justin', 'Keith', 'Kevin', 'Leonard', 'Liam', 'Lucas', 'Luke', 'Matt', 'Max', 'Michael', 'Nathan', 'Neil', 'Nicholas',
    'Oliver', 'Owen', 'Paul', 'Peter', 'Phil', 'Piers', 'Richard', 'Robert', 'Ryan', 'Sam', 'Sean', 'Sebastian', 'Simon', 'Stephen', 'Steven', 'Stewart', 'Thomas', 'Tim', 'Trevor',
    'Victor', 'Warren']

female_first_names = ['Abigail', 'Alexandra', 'Alison', 'Amanda', 'Amelia', 'Amy', 'Andrea', 'Angela', 'Anna', 'Anne', 'Audrey', 'Ava', 'Bella', 'Bernadette', 'Carol', 'Caroline', 'Carolyn',
    'Chloe', 'Claire', 'Deirdre', 'Diana', 'Diane', 'Donna', 'Dorothy', 'Elizabeth', 'Ella', 'Emily', 'Emma', 'Faith', 'Felicity', 'Fiona', 'Gabrielle', 'Grace', 'Hannah',
    'Heather', 'Irene', 'Jan', 'Jane', 'Jasmine', 'Jennifer', 'Jessica', 'Joan', 'Joanne', 'Julia', 'Karen', 'Katherine', 'Kimberly', 'Kylie', 'Lauren', 'Leah', 'Lillian', 'Lily',
    'Lisa', 'Madeleine', 'Maria', 'Mary', 'Megan', 'Melanie', 'Michelle', 'Molly', 'Natalie', 'Nicola', 'Olivia', 'Penelope', 'Pippa', 'Rachel', 'Rebecca', 'Rose', 'Ruth', 'Sally',
    'Samantha', 'Sarah', 'Sonia', 'Sophie', 'Stephanie', 'Sue', 'Theresa', 'Tracey', 'Una', 'Vanessa', 'Victoria', 'Virginia', 'Wanda', 'Wendy', 'Yvonne', 'Zoe']

last_names = ['Abraham', 'Allan', 'Alsop', 'Anderson', 'Arnold', 'Avery', 'Bailey', 'Baker', 'Ball', 'Bell', 'Berry', 'Black', 'Blake', 'Bond', 'Bower', 'Brown', 'Buckland', 'Burgess', 'Butler',
    'Cameron', 'Campbell', 'Carr', 'Chapman', 'Churchill', 'Clark', 'Clarkson', 'Coleman', 'Cornish', 'Davidson', 'Davies', 'Dickens', 'Dowd', 'Duncan', 'Dyer', 'Edmunds', 'Ellison',
    'Ferguson', 'Fisher', 'Forsyth', 'Fraser', 'Gibson', 'Gill', 'Glover', 'Graham', 'Grant', 'Gray', 'Greene', 'Hamilton', 'Hardacre', 'Harris', 'Hart', 'Hemmings', 'Henderson', 'Hill',
    'Hodges', 'Howard', 'Hudson', 'Hughes', 'Hunter', 'Ince', 'Jackson', 'James', 'Johnston', 'Jones', 'Kelly', 'Kerr', 'King', 'Knox', 'Lambert', 'Langdon', 'Lawrence', 'Lee', 'Lewis',
    'Lyman', 'MacDonald', 'Mackay', 'Mackenzie', 'MacLeod', 'Manning', 'Marshall', 'Martin', 'Mathis', 'May', 'McDonald', 'McLean', 'McGrath', 'Metcalfe', 'Miller', 'Mills', 'Mitchell',
    'Morgan', 'Morrison', 'Murray', 'Nash', 'Newman', 'Nolan', 'North', 'Ogden', 'Oliver', 'Paige', 'Parr', 'Parsons', 'Paterson', 'Payne', 'Peake', 'Peters', 'Piper', 'Poole', 'Powell',
    'Pullman', 'Quinn', 'Rampling', 'Randall', 'Rees', 'Reid', 'Roberts', 'Robertson', 'Ross', 'Russell', 'Rutherford', 'Sanderson', 'Scott', 'Sharp', 'Short', 'Simpson', 'Skinner',
    'Slater', 'Smith', 'Springer', 'Stewart', 'Sutherland', 'Taylor', 'Terry', 'Thomson', 'Tucker', 'Turner', 'Underwood', 'Vance', 'Vaughan', 'Walker', 'Wallace', 'Walsh', 'Watson',
    'Welch', 'White', 'Wilkins', 'Wilson', 'Wright', 'Young']


class OrthancTestDbPopulator:
    """
    Populates an Orthanc with a test DB
    """

    def __init__(self,
                 api_client: OrthancApiClient,
                 studies_count: int,
                 random_seed: int = None,                   # to make the generation repeatable
                 from_study_date: datetime.date = datetime.date(2000, 1, 1),     # StudyDate for generated studies
                 to_study_date: datetime.date = datetime.date(2022, 4, 21)        # StudyDate for generated studies
                 ):

        self._api_client = api_client
        self._studies_count = studies_count
        self._random_seed = random_seed
        self._patient_counter = 1
        self._from_study_date = from_study_date
        self._to_study_date = to_study_date

    def generate_patient_tags(self, tags: object) -> object:
        # generate a pseudo patient
        gender = random.choice(['M', 'F'])
        if gender == 'F':
            first_name = random.choice(female_first_names)
        else:
            first_name = random.choice(male_first_names)
        last_name = random.choice(last_names)

        tags["PatientName"] = '{0}^{1}'.format(first_name.upper(), last_name.upper())
        tags["PatientBirthDate"] = helpers.get_random_dicom_date(date_from=datetime.date(1920, 1, 1))
        tags["PatientID"] = "ID-{f}-{l}-{c:08}".format(f=first_name[:3].upper(), l=last_name[:3].upper(), c=self._patient_counter)
        tags["PatientSex"] = gender

        self._patient_counter += 1
        logger.info("created patient {id} - {name}".format(id=tags["PatientID"], name=tags["PatientName"]))

        return tags


    def generate_study_tags(self, tags: object, study_counter: int) -> object:
        tags["StudyInstanceUID"] = pydicom.uid.generate_uid(entropy_srcs=[str(study_counter), str(random.randint(0, 1000000))])
        tags["StudyDescription"] = f"Study # {study_counter:08}"
        tags["StudyDate"] = helpers.get_random_dicom_date(date_from=self._from_study_date, date_to=self._to_study_date)

        return tags

    def generate_series_tags(self, tags: object, series_counter: int, study_counter: int) -> object:
        tags["SeriesInstanceUID"] = pydicom.uid.generate_uid(entropy_srcs=[str(series_counter), str(study_counter), str(random.randint(0, 1000000))])
        tags["FrameOfReferenceUID"] = pydicom.uid.generate_uid(entropy_srcs=[str(series_counter), str(study_counter), str(random.randint(1000000, 2000000))])
        tags["SeriesDescription"] = f"Series # {series_counter:02}"
        tags["SeriesDate"] = tags["StudyDate"]
        tags["Modality"] = random.choice(["MR", "CT", "CR", "DX", "CR", "DX", "CR", "DX", "CR", "DX", "CR", "DX"])  #we want more CR and DX !

        return tags

    def generate_instance_tags(self, tags: object, instance_counter: int, series_counter: int, study_counter: int) -> object:
        tags["SOPInstanceUID"] = pydicom.uid.generate_uid(entropy_srcs=[str(instance_counter), str(series_counter), str(study_counter), str(random.randint(0, 1000000))])
        tags["InstanceNumber"] = instance_counter + 1
        tags["ContentDate"] = tags["StudyDate"]
        tags["AcquisitionDate"] = tags["StudyDate"]

        return tags

    def execute(self):
        random.seed(self._random_seed)

        tags = {}
        tags = self.generate_patient_tags(tags)

        for study_counter in range(0, self._studies_count):
            if random.randint(0, 10) > 7:  # change patients every now and then
                tags = self.generate_patient_tags(tags)

            tags = self.generate_study_tags(tags, study_counter)

            logger.info(f"-created study {tags['StudyDescription']}")

            series_count = random.randint(1, 6)
            for series_counter in range(0, series_count):
                tags = self.generate_series_tags(tags, series_counter, study_counter)

                if tags["Modality"] in ["MR", "CT"]:
                    instances_count = random.randint(50, 150)
                else:
                    instances_count = 1

                logger.info(f"--created series {tags['Modality']} with {instances_count} instances")

                for instance_counter in range(0, instances_count):
                    tags = self.generate_instance_tags(tags, instance_counter, series_counter, study_counter)

                    dicom = helpers.generate_test_dicom_file(width=2, height=2, tags=tags)
                    self._api_client.upload(buffer=dicom)


# examples:
# python orthanc_tools/orthanc_test_db_populator.py --url=http://192.168.0.10:8042 --user=user --password=pwd --studies=50 --seed=42

if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Populates an Orthanc with a test DB')
    parser.add_argument('--url', type=str, default=None, help='Orthanc url')
    parser.add_argument('--user', type=str, default=None, help='Orthanc user name')
    parser.add_argument('--password', type=str, default=None, help='Orthanc password')
    parser.add_argument('--studies', type=int, default=100, help='Number of studies to push')
    parser.add_argument('--seed', type=int, default=42, help='Random seed (to make generation repeatable)')
    args = parser.parse_args()

    url = os.environ.get("ORTHANC_URL", args.url)
    user = os.environ.get("ORTHANC_USER", args.user)
    pwd = os.environ.get("ORTHANC_PWD", args.password)

    populator = OrthancTestDbPopulator(
        api_client=OrthancApiClient(url, user=user, pwd=pwd),
        studies_count=args.studies,
        random_seed=args.seed
    )

    populator.execute()

