import gzip
import datetime
import argparse
import logging
import os
import posixpath
import subprocess
import tempfile
import time
import uuid

import paramiko
import schedule

logger = logging.getLogger(__name__)


class PostgresDumper:
    """
    Runs every day to create a gzip compressed dump of the postgres DB and write it to the destination (currently, only sftp)

    Warning:
    `postgresql-client` has to be installed before the execution of this script

    To restore:
    gzip -dc Friday.gz | pg_restore --clean -U postgres -h database -p 5432 -d postgres
    """
    def __init__(self, pg_host: str, pg_port: str, pg_db_name: str, pg_user_name: str, pg_password,
                 execution_time: str,
                 sftp_host: str, sftp_port: int, sftp_user_name: str, sftp_password: str, sftp_folder_path: str
                 ):

        if not sftp_host:
            raise ValueError("sftp_host must be configured")
        if not sftp_user_name:
            raise ValueError("sftp_user_name must be configured")
        if not sftp_folder_path:
            raise ValueError("sftp_folder_path must be configured")

        self.sftp_folder_path = sftp_folder_path.rstrip("/") or "/"
        self.sftp_password = sftp_password
        self.sftp_user_name = sftp_user_name
        self.sftp_port = int(sftp_port)
        self.sftp_host = sftp_host
        self.execution_time = execution_time
        self.pg_password = pg_password
        self.pg_user_name = pg_user_name
        self.pg_db_name = pg_db_name
        self.pg_host = pg_host
        self.pg_port = str(pg_port)

    def _stream_compressed_dump(self, remote_file):
        stderr_file = tempfile.TemporaryFile()
        process = None

        try:
            process = subprocess.Popen(
                [
                    "pg_dump",
                    "-U", self.pg_user_name,
                    "-h", self.pg_host,
                    "-p", self.pg_port,
                    "-Fc",
                    self.pg_db_name,
                ],
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                env={**os.environ, "PGPASSWORD": self.pg_password},
            )

            with gzip.GzipFile(fileobj=remote_file, mode="wb", mtime=0) as compressed_file:
                for chunk in iter(lambda: process.stdout.read(64 * 1024), b""):
                    compressed_file.write(chunk)

            return_code = process.wait()
            stderr_file.seek(0)
            error_message = stderr_file.read().decode(errors="replace").strip()

            if return_code != 0:
                raise RuntimeError(
                    f"pg_dump failed with exit code {return_code}: {error_message}"
                )
        except Exception:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            raise
        finally:
            if process is not None and process.stdout is not None:
                process.stdout.close()
            stderr_file.close()

    def stream_pg_dump_to_sftp(self):
        transport = None
        sftp = None

        day_file_name = f"{datetime.date.today().strftime('%A')}.gz"
        final_file_path = posixpath.join(self.sftp_folder_path, day_file_name)
        temporary_file_path = f"{final_file_path}.part-{uuid.uuid4().hex}"

        try:
            transport = paramiko.Transport((self.sftp_host, self.sftp_port))
            transport.connect(
                username=self.sftp_user_name,
                password=self.sftp_password,
            )
            sftp = paramiko.SFTPClient.from_transport(transport)

            with sftp.open(temporary_file_path, "wb") as remote_file:
                self._stream_compressed_dump(remote_file)

            try:
                sftp.posix_rename(temporary_file_path, final_file_path)
            except OSError as ex:
                raise RuntimeError(
                    "The SFTP server could not atomically promote the completed "
                    f"backup to {final_file_path}; the previous backup was preserved"
                ) from ex

            logger.info("Backup successfully uploaded to %s", final_file_path)
        except Exception:
            if sftp is not None and temporary_file_path is not None:
                try:
                    sftp.remove(temporary_file_path)
                except OSError:
                    pass
            logger.exception("PostgreSQL backup failed")
            raise
        finally:
            if sftp is not None:
                try:
                    sftp.close()
                except Exception:
                    logger.warning("Could not close SFTP client", exc_info=True)
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    logger.warning("Could not close SFTP transport", exc_info=True)

    def execute(self):
        logger.info("----- Initializing Postgres Dumper...")

        # Check if postgresql-client is installed
        try:
            result = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, check=True)
            logger.info(f"pg_dump version: {result.stdout.strip()}")
        except (FileNotFoundError, subprocess.CalledProcessError) as ex:
            raise RuntimeError(
                "pg_dump is unavailable; install postgresql-client before running this tool"
            ) from ex

        if self.execution_time is None:
            # unit test case
            self.stream_pg_dump_to_sftp()
        else:
            # regular (prod) case
            schedule.every().day.at(self.execution_time).do(self.stream_pg_dump_to_sftp)
            while True:
                schedule.run_pending()
                time.sleep(1)


if __name__ == '__main__':
    level = logging.INFO
    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Periodically dumps Postgres DB to an SFTP server.')
    parser.add_argument('--pg_host', type=str, default='orthanc-db', help='Postgres hostname')
    parser.add_argument('--pg_port', type=str, default='5432', help='Postgres port number')
    parser.add_argument('--pg_db_name', type=str, default='postgres', help='Postgres database name')
    parser.add_argument('--pg_user_name', type=str, default='postgres', help='Postgres username')
    parser.add_argument('--pg_password', type=str, default='', help='Postgres password')
    parser.add_argument('--execution_time', type=str, default='01:30', help='Time for script execution (format: 23:30 or 23:30:14)')
    parser.add_argument('--sftp_host', type=str, default=None, help='sFTP server hostname')
    parser.add_argument('--sftp_port', type=str, default='22', help='sFTP server port number')
    parser.add_argument('--sftp_user_name', type=str, default=None, help='sFTP server user name')
    parser.add_argument('--sftp_password', type=str, default=None, help='sFTP server password')
    parser.add_argument('--sftp_folder_path', type=str, default=None, help='sFTP server folder path')
    args = parser.parse_args()

    pg_host = os.environ.get("PG_HOST", args.pg_host)
    pg_port = os.environ.get("PG_PORT", args.pg_port)
    pg_db_name = os.environ.get("PG_DB_NAME", args.pg_db_name)
    pg_user_name = os.environ.get("PG_USER_NAME", args.pg_user_name)
    pg_password = os.environ.get("PG_PASSWORD", args.pg_password)
    execution_time = os.environ.get("EXECUTION_TIME", args.execution_time)
    if execution_time == '':
        execution_time = None
    sftp_host = os.environ.get("SFTP_HOST", args.sftp_host)
    sftp_port = int(os.environ.get("SFTP_PORT", args.sftp_port))
    sftp_user_name = os.environ.get("SFTP_USER_NAME", args.sftp_user_name)
    sftp_password = os.environ.get("SFTP_PASSWORD", args.sftp_password)
    sftp_folder_path = os.environ.get("SFTP_FOLDER_PATH", args.sftp_folder_path)

    dumper = PostgresDumper(pg_host, pg_port, pg_db_name, pg_user_name, pg_password, execution_time,
                            sftp_host, sftp_port, sftp_user_name, sftp_password, sftp_folder_path)

    dumper.execute()
