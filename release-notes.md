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
- `PacsMigrator`: fixed arg bug (exit_on_error)

v 0.9.6
=======
- `PacsMigrator`: fixed arg bug

v 0.9.5
=======
- `PacsMigrator`: added `exit_on_error` parameter

v 0.9.4
=======
- Forget it

v 0.9.3
=======
- `OrthancCleaner` and `OrthancComparator`: fixed required arg bug

v 0.9.2
=======
- `OrthancCleaner`: updated setup.py

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

v 0.8.7
=======

- Forget it

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