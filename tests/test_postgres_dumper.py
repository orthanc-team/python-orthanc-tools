import gzip
import io
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from orthanc_tools.postgres_dumper import PostgresDumper


class NonClosingBytesIO(io.BytesIO):
    def close(self):
        self.flushed_on_close = True


class FakeProcess:
    def __init__(self, stdout, return_code):
        self.stdout = io.BytesIO(stdout)
        self._configured_return_code = return_code
        self.returncode = None
        self.terminated = False

    def wait(self):
        self.returncode = self._configured_return_code
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -1


class TestPostgresDumper(unittest.TestCase):
    def setUp(self):
        self.dumper = PostgresDumper(
            pg_host="database",
            pg_port=5432,
            pg_db_name="orthanc",
            pg_user_name="backup",
            pg_password="database-secret",
            execution_time=None,
            sftp_host="backup",
            sftp_port=22,
            sftp_user_name="uploader",
            sftp_password="sftp-secret",
            sftp_folder_path="/backups/",
        )

        self.transport = mock.MagicMock()
        self.sftp = mock.MagicMock()
        self.remote_file = NonClosingBytesIO()
        self.sftp.open.return_value = self.remote_file

        self.transport_patch = mock.patch(
            "orthanc_tools.postgres_dumper.paramiko.Transport",
            return_value=self.transport,
        )
        self.sftp_patch = mock.patch(
            "orthanc_tools.postgres_dumper.paramiko.SFTPClient.from_transport",
            return_value=self.sftp,
        )
        self.uuid_patch = mock.patch(
            "orthanc_tools.postgres_dumper.uuid.uuid4",
            return_value=SimpleNamespace(hex="test-run"),
        )
        self.transport_patch.start()
        self.sftp_patch.start()
        self.uuid_patch.start()
        self.addCleanup(self.transport_patch.stop)
        self.addCleanup(self.sftp_patch.stop)
        self.addCleanup(self.uuid_patch.stop)

    def _popen(self, dump, return_code=0, stderr=b"", captured_env=None):
        def create_process(*args, **kwargs):
            kwargs["stderr"].write(stderr)
            if captured_env is not None:
                captured_env.update(kwargs["env"])
            return FakeProcess(dump, return_code)

        return create_process

    def test_successful_dump_is_compressed_then_atomically_promoted(self):
        dump = b"postgres custom-format dump"
        captured_env = {}

        with mock.patch.dict(os.environ, {"PATH": "test-path"}, clear=True):
            with mock.patch(
                "orthanc_tools.postgres_dumper.subprocess.Popen",
                side_effect=self._popen(dump, captured_env=captured_env),
            ):
                self.dumper.stream_pg_dump_to_sftp()

        temporary_path = self.sftp.open.call_args.args[0]
        final_path = self.sftp.posix_rename.call_args.args[1]
        self.assertTrue(temporary_path.endswith(".gz.part-test-run"))
        self.assertTrue(final_path.startswith("/backups/"))
        self.assertTrue(final_path.endswith(".gz"))
        self.assertEqual(dump, gzip.decompress(self.remote_file.getvalue()))
        self.assertEqual("test-path", captured_env["PATH"])
        self.assertEqual("database-secret", captured_env["PGPASSWORD"])
        self.sftp.posix_rename.assert_called_once_with(
            temporary_path,
            final_path,
        )
        self.sftp.remove.assert_not_called()
        self.sftp.close.assert_called_once_with()
        self.transport.close.assert_called_once_with()

    def test_failed_pg_dump_removes_partial_file_and_preserves_final_name(self):
        self.sftp.close.side_effect = OSError("close failed")

        with mock.patch(
            "orthanc_tools.postgres_dumper.subprocess.Popen",
            side_effect=self._popen(
                b"incomplete",
                return_code=1,
                stderr=b"permission denied",
            ),
        ):
            with self.assertLogs(
                "orthanc_tools.postgres_dumper",
                level="ERROR",
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "pg_dump failed with exit code 1: permission denied",
                ):
                    self.dumper.stream_pg_dump_to_sftp()

        temporary_path = self.sftp.open.call_args.args[0]
        self.sftp.remove.assert_called_once_with(temporary_path)
        self.sftp.posix_rename.assert_not_called()

    def test_failed_atomic_promotion_keeps_previous_backup(self):
        self.sftp.posix_rename.side_effect = OSError("unsupported")

        with mock.patch(
            "orthanc_tools.postgres_dumper.subprocess.Popen",
            side_effect=self._popen(b"complete dump"),
        ):
            with self.assertLogs(
                "orthanc_tools.postgres_dumper",
                level="ERROR",
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "previous backup was preserved",
                ):
                    self.dumper.stream_pg_dump_to_sftp()

        temporary_path = self.sftp.open.call_args.args[0]
        self.sftp.remove.assert_called_once_with(temporary_path)

    def test_connection_error_is_not_masked_by_cleanup(self):
        self.transport_patch.stop()

        with mock.patch(
            "orthanc_tools.postgres_dumper.paramiko.Transport",
            side_effect=OSError("offline"),
        ):
            with self.assertLogs(
                "orthanc_tools.postgres_dumper",
                level="ERROR",
            ):
                with self.assertRaisesRegex(OSError, "offline"):
                    self.dumper.stream_pg_dump_to_sftp()

    def test_missing_pg_dump_raises_runtime_error(self):
        with mock.patch(
            "orthanc_tools.postgres_dumper.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with self.assertRaisesRegex(RuntimeError, "pg_dump is unavailable"):
                self.dumper.execute()


if __name__ == "__main__":
    unittest.main()
