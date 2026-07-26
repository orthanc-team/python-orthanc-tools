# python-orthanc-tools

A set of python tools to ease Orthanc scripting.

Functionalities are very limited now !  Backward compat will break a lot in the near future !

## Installation

```shell
pip3 install orthanc-tools
```

Docker images in examples should use the package version you deploy. In this checkout, the package version is `0.19.1`. In the parent `/docker` repository, production stacks build this submodule as the local image `python-orthanc-tools:local`.


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
python3 -m orthanc_tools.orthanc_cloner --source_url=http://192.168.0.10:8042 --source_user=user --source_pwd=pwd --dest_url=http://192.168.0.10:8042 --dest_user=user --dest_pwd=pwd --timezone=Europe/Paris --run_schedule='{"Monday-Friday": ["0-7", "18-24"], "Saturday-Sunday": ["0-24"]}'
```

or, inside a docker-compose file:
```yaml
services:
    orthanc-cloner:
        image: orthancteam/python-orthanc-tools:0.19.1
        volumes: ["orthanc-cloner:/status"]
        environment:
            TZ: "Etc/UTC"
            RUN_SCHEDULE: '{"Monday-Friday": ["0-7", "18-24"], "Saturday-Sunday": ["0-24"]}'
            SOURCE_URL: "http://orthanc-a:8042"
#            SOURCE_USER: "user"
#            SOURCE_PWD: "pwd"
            DEST_URL: "http://orthanc-b:8042"
#            DEST_USER: "user"
#            DEST_PWD: "pwd"
            MODE: "Default"
            PERSIST_STATE_PATH: "/status/status.txt"
            WORKER_THREADS_COUNT: "6"
#            VERBOSE_ENABLED: "true"
            ERROR_FOLDER_PATH: "/status"
            MAX_RETRIES: "3"
            TRANSFER_TIMEOUT: "300"  # timeout in seconds for download/upload operations
        entrypoint: python -m orthanc_tools.orthanc_cloner
volumes:
    orthanc-cloner:  

```

`TRANSFER_TIMEOUT` / `--transfer_timeout` applies to Default-mode instance download/upload calls.
Peer, transfer-plugin, and DICOM modes use the corresponding Orthanc operation behavior.

### OrthancCloner performance

Here are a set of measures performed during a long transfer between 2 VMs running on Azure using OrthancCloner v 0.6.3.

The source Orthanc (v1.9.0) is running on a 4 vCPU VM with 16GB RAM.  Postgresql is running on the same VM and DICOM files are stored on data disks are attached to the VM.

The destination Orthanc (v1.11.2) is running on a 4 vCPU VM with 16GB RAM.  It is using a flexible managed Postgresql server and an object storage to store DICOM files.

| Cloner Mode                                      | WorkersThreadCount | throughput [GB/h] | throughput [instances/h] |
|--------------------------------------------------|-------------------:|------------------:|-------------------------:|
| Default                                          |                 12 |                38 |                        ? |
| Default                                          |                 18 |                67 |                  142.000 |
| Default                                          |                 24 |                66 |                  160.000 |
| Transfer, Transfers.Threads=6, ConcurrentJobs=2  |                  3 |                20 |                        ? |
| Transfer, Transfers.Threads=6, ConcurrentJobs=12 |                  6 |                15 |                        ? | 



## import files from a folder from a Docker container

```
$ docker exec -it xxxx bash

/# pip3 install orthanc-tools

/# python3 -m orthanc_tools.orthanc_folder_importer --folder_path=/import --url=http://localhost:8042 --user=test --password=test --skip_extensions=.cne,.bmp,.ini --worker_threads_count=5

```

The `--skip_extensions` flag (or `SKIP_EXTENSIONS` env var) accepts a comma-separated list of file
extensions to ignore during import (e.g. `.cne,.bmp,.ini`).

The importer is resilient to short Orthanc restarts: if a connection is lost, all worker threads pause
for a bounded reconnect window and resume once Orthanc is reachable again. If Orthanc stays unreachable
after that window, the current upload attempt is treated as failed and follows the normal retry/error-log flow.

For importer error logging, use `ERRORS_PATH` to point to a log file. If you set
`ERROR_FOLDER_PATH`, the importer writes to `errors.txt` inside that folder.


## Implement a simple forwarder

The forwarder simply forwards the content of an Orthanc to another DICOM destination and then, deletes
the instances.  This is usefull for, e.g. implementing an Inbox in front of a PACS that does some
`IngestTranscoding` and/or applies sanitization in a lua script or a python plugin.

When using `--trigger=StableStudy`, the forwarder only handles studies after Orthanc reports them as
stable. Configure Orthanc's `StableAge` on the source Orthanc to control how long Orthanc waits after
the last received instance before a study is considered complete. For example, `StableAge: 60` waits
about one minute after the last incoming instance before forwarding can start.

from a shell (single destination):

```shell
python3 -m orthanc_tools.orthanc_forwarder --source_url=http://192.168.0.10:8042 --source_user=user --source_pwd=pwd --destination=target_modality_alias --trigger=StableStudy
```

### Multiple destinations

You can forward to multiple destinations at once. Each destination can optionally override the default mode
using the `alias:mode` syntax. With the CLI, you can pass one `--destination` flag per destination or
comma-separate multiple destinations in one flag:

```shell
# Forward to two DICOM destinations
python3 -m orthanc_tools.orthanc_forwarder --source_url=http://localhost:8042 --destination=modality_a --destination=modality_b --trigger=StableStudy

# Forward to one peer and one DICOM destination with different modes
python3 -m orthanc_tools.orthanc_forwarder --source_url=http://localhost:8042 --destination=peer_a:peering --destination=modality_b:dicom --trigger=StableStudy

# Equivalent comma-separated form
python3 -m orthanc_tools.orthanc_forwarder --source_url=http://localhost:8042 --destination=peer_a:peering,modality_b:dicom --trigger=StableStudy

# Forward everything to two destinations, plus only AI-tagged studies to a third one
python3 -m orthanc_tools.orthanc_forwarder --source_url=http://localhost:8042 --destination=peer_a:peering --destination=modality_b:dicom --destination=ai_service:dicom:substring:AI --trigger=StableStudy
```

Using environment variables (useful in docker-compose):

- `DESTINATION`: single destination alias (backward compatible)
- `DESTINATIONS`: comma-separated list of destinations with optional mode overrides and Study Description filters (e.g. `peer_a:peering,modality_b:dicom,ai_service:dicom:regex:^AI[ _-]`)
- `MODE`: default forwarding mode when no per-destination override is specified

Study Description filters are evaluated per study and are case-insensitive:

- `alias:mode:substring:pattern`: forward only if `StudyDescription` contains `pattern`
- `alias:mode:regex:pattern`: forward only if `StudyDescription` matches the regex
- `alias::substring:pattern`: use the global `MODE` with a Study Description filter

If a filter pattern contains commas in `DESTINATIONS`, wrap that destination entry in double quotes, for example:
`DESTINATIONS='peer_a:peering,"ai_service:dicom:substring:CT, ABDOMEN"'`

The same quoting rule applies when comma-separating multiple destinations in one CLI flag.

If a study has no `StudyDescription`, filtered destinations are skipped while unfiltered destinations still receive the study.
If no destination is eligible after filtering, the source data is kept and marked terminal so it is not retried forever.


## migrate DICOM Data from a modality to another

More info in the [PacsMigrator class](orthanc_tools/pacs_migrator.py)
```
$ docker exec -it xxxx bash

/# pip3 install orthanc-tools

/# python3 -m orthanc_tools.pacs_migrator --url=http://localhost:8042 --user=user --password=pwd --destination_modality=orthanc-debug --from_study_date=20000101 --to_study_date=20191231 --timezone=Europe/Paris --run_schedule='{"Monday-Friday": ["0-7", "18-24"], "Saturday-Sunday": ["0-24"]}'

```

## compare DICOM Data found in Orthanc and in a remote modality

Running in a Docker environment:
```
$ docker run -d --name comparator --network=mysetup_default python:3.14 bash -c "pip3 install orthanc-tools && python3 -u -m orthanc_tools.orthanc_comparator --level=Instance --url=http://pacs-2022:8042 --modality=pacs-2017 --from_study_date=20220201 --to_study_date=20220302 --transfer_missing_to_modality --ignore_missing_from_orthanc --run_only_at_night_and_weekend --night_start_hour=19 --night_end_hour=6"

```

## uploading a Test DB in Orthanc 

The OrthancTestDbPopulator generates test images and uploads them in Orthanc.
All images have only 4 pixels and take a minimum amount of space on disk. 
By default, the generator always generates the same data, use a different seed if you need variation.

From a shell:

```shell
python3 -m orthanc_tools.orthanc_test_db_populator --url=http://192.168.0.10:8042 --user=user --password=pwd --studies=5000 --series=2 --instances=100 --workers=5 --api_key=1234 --from_study_date=20150101 --to_study_date=20151231 --seed=42 --image_content_type=Random/Flat --image_width=256 --image_height=256
```

## purge old studies from an Orthanc
Allows to clean the Orthanc by deleting the oldest studies according to the labels applied on them.

With that sample, all studies with the LABEL1 and older than 6 weeks will be deleted
all studies with the LABEL2 and older than 12 weeks will be deleted.

```
LABEL1,6
LABEL2,12
```
The script will be executed every day at 2:30 (24 format!)

```shell
python3 -m orthanc_tools.orthanc_cleaner --url=http://localhost:8042 --user=orthanc --password=orthanc --execution_time=2:30 --labels_file_path=./tests/stimuli/labels.csv
```

## Deploy an HL7 server parsing ORM^O01 messages to create and store worklists files in a folder
```
   hl7-server:
        image: orthancteam/python-orthanc-tools:0.19.1
        ports: ["2575:2575"]
        volumes: ["/worklists:/worklists"]
        restart: unless-stopped
        entrypoint: ["python", "-m", "orthanc_tools.hl7_worklist_server_for_orthanc"]
```
Then, add this env var to Orthanc:

`ORTHANC__WORKLISTS__DATABASE: /var/lib/orthanc/worklists`
