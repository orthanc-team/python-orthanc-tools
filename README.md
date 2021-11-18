# python-orthanc-tools

A set of python tools to ease Orthanc scripting.

Functionalities are very limited now !  Backward compat will break a lot in the near future !

Examples:

```
from orthanc_tools import OrthancCloner
from orthanc_api_client import OrthancApiClient

orthanc_a = OrthancApiClient('http://localhost:8042', user='orthanc', pwd='orthanc')
orthanc_b = OrthancApiClient('http://localhost:8043', user='orthanc', pwd='orthanc')

cloner = OrthancCloner(source=orthanc_a, destination=orthanc_b)
cloner.execute()

```

## import files from a folder from a Docker container

```
$ docker exec -it xxxx bash

/# pip3 install orthanc-tools

/# python3 -m orthanc_tools.orthanc_folder_importer --folder=/import --url=http://localhost:8042 --user=test --pwd=test

```