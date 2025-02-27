import sys
import datetime
import paramiko
import time, os
import argparse
import logging
import schedule
import subprocess
logger = logging.getLogger(__name__)

class PostgresDumper:
    """
    Runs every day to create a gzip compressed dump of the postgres DB and write it to the destination (currently, only sftp)

    Warning:
    `postgresql-client` has to be installed before the execution of this script

    To restore:
    pg_restore --clean -U postgres -h 172.21.0.3 -p 5432 -d postgres Friday
    """
    def __init__(self, pg_host: str, pg_port: str, pg_db_name: str, pg_user_name: str, pg_password,
                 execution_time: str,
                 sftp_host: int, sftp_port: str, sftp_user_name: str, sftp_password: str, sftp_folder_path: str
                 ):

        self.sftp_folder_path = sftp_folder_path
        # remove last char if this is a slash
        if self.sftp_folder_path[-1:] == '/':
            self.sftp_folder_path = self.sftp_folder_path[:-1]
        self.sftp_password = sftp_password
        self.sftp_user_name = sftp_user_name
        self.sftp_port = sftp_port
        self.sftp_host = sftp_host
        self.execution_time = execution_time
        self.pg_password = pg_password
        self.pg_user_name = pg_user_name
        self.pg_db_name = pg_db_name
        self.pg_host = pg_host
        self.pg_port = pg_port

    def stream_pg_dump_to_sftp(self):
        try:
            # Establish SFTP connection
            transport = paramiko.Transport((self.sftp_host, self.sftp_port))
            transport.connect(username=self.sftp_user_name, password=self.sftp_password)
            sftp = paramiko.SFTPClient.from_transport(transport)

            # Build full file path: we use the name fo the day, so that only 7 files are kept and there is no need
            # to clean up ourselves (files are overwritten the next week)
            sftp_file_path = f"{self.sftp_folder_path}/{datetime.date.today().strftime('%A')}.gz"

            # Open a remote file for writing
            # TODO: given that the 'sftp.open()' works the same way as a regular file, we could make this script working for both cases
            with sftp.open(sftp_file_path, "wb") as remote_file:
                # Run pg_dump and capture output
                # Let's be honest, ChatGPT helped a lot on this ;-)
                process = subprocess.Popen(
                    ["pg_dump", "-U", self.pg_user_name, "-h", self.pg_host, "-p", self.pg_port, "-Fc", self.pg_db_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={"PGPASSWORD": self.pg_password}
                )

                # Compress the dump (the 'Fc' parameter of the pg_dump command is not very efficient)
                gzip_process = subprocess.Popen(["gzip"], stdin=process.stdout, stdout=subprocess.PIPE)

                # Stream gzip output directly to SFTP
                for chunk in iter(lambda: gzip_process.stdout.read(4096), b""):
                    remote_file.write(chunk)

                # Ensure the process completes
                process.stdout.close()
                process.wait()

                # Check for errors
                if process.returncode != 0:
                    error_message = process.stderr.read().decode()
                    logger.error(f"pg_dump failed: {error_message}")

            logger.info(f"Backup successfully uploaded to {self.sftp_folder_path}")

        except Exception as e:
            logger.error(f"Error: {e}")
            sys.exit(-1)

        finally:
            sftp.close()
            transport.close()


    def execute(self):
        logger.info("----- Initializing Postgres Dumper...")

        # Check if postgresql-client is installed
        try:
            result = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, check=True)
            logger.info(f"pg_dump version: {result.stdout.strip()}")
        except FileNotFoundError:
            logger.error("it seems that pg_dump is NOT installed, plase install it before running this script (apt install postgresql-client)")
            sys.exit(-1)

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
    parser.add_argument('--pg_host', type=str, default='http://orthanc-db', help='Postgres hostname')
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
    if execution_time is '':
        execution_time = None
    sftp_host = os.environ.get("SFTP_HOST", args.sftp_host)
    sftp_port = int(os.environ.get("SFTP_PORT", args.sftp_port))
    sftp_user_name = os.environ.get("SFTP_USER_NAME", args.sftp_user_name)
    sftp_password = os.environ.get("SFTP_PASSWORD", args.sftp_password)
    sftp_folder_path = os.environ.get("SFTP_FOLDER_PATH", args.sftp_folder_path)

    dumper = PostgresDumper(pg_host, pg_port, pg_db_name, pg_user_name, pg_password, execution_time,
                            sftp_host, sftp_port, sftp_user_name, sftp_password, sftp_folder_path)

    dumper.execute()
