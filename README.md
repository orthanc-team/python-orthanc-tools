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
from orthanc_tools import OrthancCloner
from orthanc_api_client import OrthancApiClient

orthanc_a = OrthancApiClient('http://localhost:8042', user='orthanc', pwd='orthanc')
orthanc_b = OrthancApiClient('http://localhost:8043', user='orthanc', pwd='orthanc')

cloner = OrthancCloner(source=orthanc_a, destination=orthanc_b)
cloner.execute(existing_changes_only=False)

```

from a shell:

```shell
python3 -m orthanc_tools.orthanc_cloner --source_url=http://192.168.0.10:8042 --source_user=user --source_pwd=pwd --dest_url=http://192.168.0.10:8042 --dest_user=user --dest_pwd=pwd
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

```
$ docker exec -it xxxx bash

/# pip3 install orthanc-tools

/# python3 -m orthanc_tools.orthanc_comparator --url=http://localhost:8042 --user=user --password=pwd --modality=orthanc-debug --from_study_date=20000101 --to_study_date=20191231 --run_only_at_night_and_weekend --night_start_hour=18 --night_end_hour=6

```

## uploading a Test DB in Orthanc 

The OrthancTestDbPopulator generates test images and uploads them in Orthanc.
All images have only 4 pixels and take a minimum amount of space on disk. 
By default, the generator always generates the same date, use a different seed if you need variation.
from a shell:

```shell
python3 -m orthanc_tools.orthanc_test_db_populator --url=http://192.168.0.10:8042 --user=user --password=pwd --studies=5000 --seed=42
```
