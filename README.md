# python-orthanc-tools

A set of python tools to ease Orthanc scripting.

Functionalities are very limited now !  Backward compat will break a lot in the near future !

## Installation

```shell
pip3 install orthanc-tools
```


## cloning an Orthanc to another

The cloners copies everything that is currently in the source Orthanc into the destination Orthanc and,
once this is done continues the cloning process for every DICOM instance that is received by the source.

from a python script:

```python
from orthanc_tools import OrthancCloner, ClonerMode
from orthanc_api_client import OrthancApiClient

orthanc_a = OrthancApiClient('http://localhost:8042', user='orthanc', pwd='orthanc')
orthanc_b = OrthancApiClient('http://localhost:8043', user='orthanc', pwd='orthanc')

cloner = OrthancCloner(source=orthanc_a, destination=orthanc_b)
cloner.execute(existing_changes_only=False)

# if the destination is declared as a peer:
cloner = OrthancCloner(source=orthanc_a, destination_peer='orthanc-b', mode=ClonerMode.TRANSFER)
cloner.execute(existing_changes_only=False)

```

from a shell:

```shell
python3 -m orthanc_tools.orthanc_cloner --source_url=http://192.168.0.10:8042 --source_user=user --source_pwd=pwd --dest_url=http://192.168.0.10:8042 --dest_user=user --dest_pwd=pwd --run_only_at_night_and_weekend=true --night_start_hour=19 --night_end_hour=6
```

or, inside a docker-compose file:
```yaml
version: "3"
services:
    orthanc-cloner:
        image: orthancteam/python-orthanc-tools:0.6.0
        volumes: ["orthanc-cloner:/status"]
        environment:
            RUN_ONLY_AT_NIGHT_AND_WEEKEND: "true"
            NIGHT_START_HOUR: "15"
            NIGHT_END_HOUR: "6"
            SOURCE_URL: "http://orthanc-a:8042"
#            SOURCE_USER: "user"
#            SOURCE_PWD: "pwd"
            DEST_URL: "http://orthanc-b:8042"
#            DEST_USER: "user"
#            DEST_PWD: "pwd"
            MODE: "Default"
            PERSIST_STATE_PATH: "/status/status.txt"
            WORKERS_THREAD_COUNT: "6"
#            VERBOSE_ENABLED: "true"
            ERROR_FOLDER_PATH: "/status"
            MAX_RETRIES: "3"
        entrypoint: python -m orthanc_tools.orthanc_cloner
volumes:
    orthanc-cloner:  

```

## import files from a folder from a Docker container

```
$ docker exec -it xxxx bash

/# pip3 install orthanc-tools

/# python3 -m orthanc_tools.orthanc_folder_importer --folder=/import --url=http://localhost:8042 --user=test --password=test --skip_extensions=.cne,.bmp,.ini

```


## migrate DICOM Data from a modality to another

More info in the [PacsMigrator class](orthanc_tools/pacs_migrator.py)
```
$ docker exec -it xxxx bash

/# pip3 install orthanc-tools

/# python3 -m orthanc_tools.pacs_migrator --url=http://localhost:8042 --user=user --password=pwd --destination_modality=orthanc-debug --from_study_date=20000101 --to_study_date=20191231 --run_only_at_night_and_weekend --night_start_hour=18 --night_end_hour=6

```

## compare DICOM Data found in Orthanc and in a remote modality

Running in a Docker environment:
```
$ docker run -d --name comparator --network=mysetup_default python:3.9 bash -c "pip3 install orthanc-tools && python3 -u -m orthanc_tools.orthanc_comparator --level=Instance --url=http://pacs-2022:8042 --modality=pacs-2017 --from_study_date=20220201 --to_study_date=20220302 --transfer_missing_to_modality --ignore_missing_from_orthanc --run_only_at_night_and_weekend --night_start_hour=19 --night_end_hour=6"

```

## uploading a Test DB in Orthanc 

The OrthancTestDbPopulator generates test images and uploads them in Orthanc.
All images have only 4 pixels and take a minimum amount of space on disk. 
By default, the generator always generates the same date, use a different seed if you need variation.

From a shell:

```shell
python3 -m orthanc_tools.orthanc_test_db_populator --url=http://192.168.0.10:8042 --user=user --password=pwd --studies=5000 --seed=42
```
