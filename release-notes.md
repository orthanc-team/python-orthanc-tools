v 0.14.4
========
- `OrthancFolderImporter` update: allows to modify/filter instance before upload.

v 0.14.3
========
- Added `--mode` argument to `OrthancForwarder`.

v 0.14.2
========
- `LabelModifier` tool added. Allows to fix a typo in a label with handling of the permissions. 

v 0.13.11
========
- `OrthancTestDbPopulator` script now accepts `--from_study_date` and `--to_study_date` arguments.

v 0.13.10
========
- `OrthancFolderImporter` uses worker threads.
- `OrthancFolderImporter` is more robust for zip files.

v 0.13.7
========
- `OrthancFolderImporter` can now logs errors and state.

v 0.13.4
========
- `OrthancForwarder` can now work with multipler worker_threads.

v 0.13.3
========
- Improved `OrthancTestDbPopulator` to generate more Tags and more different values to have 
  more representative larger SQL indexes.  It also generates more MR/CT series with more instances.

v 0.13.1
========
- improved `orthanc_uploader` with retry and immediate labeling 

v 0.13.0
========
- fixed an incompatibility with pydicom 3.0.0

v 0.12.18
========
- improved `OrthancCleaner` to handle `LimitFindResults`

v 0.12.17
========
- added `OrthancWarmer` tool (for tests/debug purposes)

v 0.12.15
========
- added `Dicom` mode for the `OrthancCloner`

v 0.12.14
========
- added `orthanc_space_threshold` parameter to the `PacsMigrator`

v 0.12.13
========
- added api-key arg (and env var) as a way to authenticate to Orthanc for the tools

v 0.12.12
========
- upgraded `orthanc_uploader` to unzip before upload

v 0.12.11
========
- forget it

v 0.12.10
========
- added periodic mode to the `Comparator` 

v 0.12.9
========
- improved `Replicator` to retry broker connection

v 0.12.8
========
- added a way to call the `OrthancForwarder` directly from the shell

v 0.12.7
========
- upgraded `Hl7WorklistParser` to correctly handle the values (including 'U') for `PatientSex` segment

v 0.12.6
========
- upgraded `Hl7WorklistParser` to handle `ScheduledProcedureStepStartDate` and `ScheduledProcedureStepStartTime` in OBR segment from assistovet

v 0.12.5
========
- updated `orthanc-api-client` to 0.15.1

v 0.12.3
========
- added `orthanc_uploader` tool

v 0.11.0
========
- added `ids_migrator` tool

v 0.10.2
========
- `OrthancForwarder`: fixed forwarding of series > 1 GB in `DICOM_WEB_SERIES_BY_SERIES` mode

v 0.10.1
========
- added delay before retry in the `pacs_migrator` c-move

v 0.10.0
========
- added a new tool: `hl7_worklist_server_for_orthanc`

v 0.9.15
========
- `OrthancComparator`: added logging of errors in a file

v 0.9.14
========
- `DicomWorklistBuilder`: added fields and tests for Veterinarians purposes

v 0.9.13
========
- `OrthancComparator`: added series by series mode for retrieve

v 0.9.12
========
- `OrthancComparator`: added throttling

v 0.9.11
========
- `OrthancComparator`: added retry for MOVE and STORE

v 0.9.10
========
- `OrthancForwarder`: fixed retry bug

v 0.9.9
=======
- added `OrthancReplicator`

v 0.9.8
=======
- `OrthancForwarder`: added 2 callbacks `on_instances_set_forwarded` and `on_instances_set_forward_error`

v 0.9.7
=======
- `PacsMigrator`: added `exit_on_error` parameter

v 0.9.3
=======
- `OrthancCleaner` and `OrthancComparator`: fixed required arg bug

v 0.9.1
=======
- `OrthancCleaner`: no longer deletes old studies if they were uploaded during the retention period

v 0.9.0
=======
- `OrthancCleaner`: added OrthancCleaner

v 0.8.9
=======
- `OrthancTestDbPopulator`: now labelling studies

v 0.8.8
=======

- `OrthancMonitor`: fixed monitor

v 0.8.6
=======

- `OrthancTestDbPopulator`: new feature: number of series/instances

v 0.8.5
=======

- `PacsMigrator`: fix push_message method

v 0.8.4
=======

- `OrthancForwarder`: added error logs + retry in case of ConnectionError
- `OrthancForwarder`: removed `worker_threads_count` that was not used anymore

v 0.8.3
=======

- `OrthancForwarder`: not using `OrthancMonitor` anymore
- `OrthancForwarder`: fixed retries

v 0.8.2
=======

- `OrthancForwarder`: fix logging

v 0.8.1
=======

- `OrthancForwarder`: handle content stored in Orthanc at start
- uniformized logger names to `__name__`
- BREAKING_CHANGE: do not pass logger between classes, always use the default module logger

v 0.8.0
=======

- added `OrthancForwarder` class
- BREAKING_CHANGE: moved helpers classes into `helpers` package: `OldFilesDeleter`, `Scheduler`, `TimeOut`, `Timer`

v 0.7.4
=======
- added bypass of 404 errors in the cloner
- fixed parsing error for MAX_RETRIES arg in cloner

v 0.7.3
=======
- added oru messages handler (for reports) in hl7 lib
- clean up of hl7 lib

v 0.7.2
=======
- really fix CI and build problems

v 0.7.1
=======
- fix CI and build problems

v 0.7.0
=======
- added hl7 tools

v 0.6.5
=======
- uses orthanc-api-client v 0.8.0
- `OrthancCloner`: fix retry bug

v 0.6.4
=======
- `OrthancMonitor`: no logs for unprocessed changes

v 0.6.3
=======
- BREAKING_CHANGE: `OrthancMonitor` handlers now receive `change_id` as the first argument and shall throw in case of failures.
  They should not return `True` or `False`.
- `OrthancCloner`: more acurate logs

v 0.6.2
=======

- CI publishes orthancteam/python-orthanc-tools Docker image
- fixes incompatibilities with orthanc-api-client v 0.7.1
- `OrthancCloner` `Transfer` mode now triggers on `StableStudy` event instead of `NewStudy`
- `OrthancCloner` now implements retries in case of failure and store failures in a specific folder. 

v 0.6.1
=======

- uses orthanc-api-client v 0.7.1 to fix `OrthancCloner` with reverse-proxies

v 0.6.0
=======

- added a scheduler for `OrthancCloner` to allow running at night and weekends.
- BREAKING_CHANGE: `OrthancCloner` constructor: renamed `workers_count` into `worker_threads_count`

v 0.5.1
=======

- added 'mode' for OrthancCloner: `ClonerMode.DEFAULT, ClonerMode.PEERING, ClonerMode.TRANSFER`

v 0.4.9
=======

- uses orthanc-api-client v 0.5.8

v 0.4.7
=======
-  pacs_migrator - added retry for transfer from modality to aet

v 0.4.7
=======
- uses orthanc-api-client v 0.5.0