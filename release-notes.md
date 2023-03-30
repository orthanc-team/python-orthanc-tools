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