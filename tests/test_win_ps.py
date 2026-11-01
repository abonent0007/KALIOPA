"""Общий запуск PowerShell: разбор JSON и ошибки без падения вызывающего."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_win_ps  # noqa: E402


class JsonRowsTests(unittest.TestCase):
    def test_empty_output_is_an_empty_list(self):
        self.assertEqual([], nova_win_ps.json_rows(""))
        self.assertEqual([], nova_win_ps.json_rows(None))

    def test_single_object_becomes_a_list(self):
        self.assertEqual([{"a": 1}], nova_win_ps.json_rows('{"a": 1}'))

    def test_non_object_rows_are_dropped(self):
        self.assertEqual([{"a": 1}], nova_win_ps.json_rows('[{"a": 1}, 5, null]'))

    def test_broken_json_raises_a_clear_error(self):
        with self.assertRaises(ValueError):
            nova_win_ps.json_rows("not json")


class RunTests(unittest.TestCase):
    def test_stdout_is_returned(self):
        done = mock.Mock(returncode=0, stdout="ok\n", stderr="")
        with mock.patch.object(nova_win_ps.subprocess, "run", return_value=done):
            self.assertEqual("ok\n", nova_win_ps.run("Write-Output ok"))

    def test_nonzero_exit_becomes_runtime_error(self):
        done = mock.Mock(returncode=1, stdout="", stderr="access denied")
        with mock.patch.object(nova_win_ps.subprocess, "run", return_value=done):
            with self.assertRaises(RuntimeError):
                nova_win_ps.run("Set-DnsClientServerAddress")

    def test_launch_failure_becomes_runtime_error(self):
        with mock.patch.object(nova_win_ps.subprocess, "run", side_effect=OSError("no powershell")):
            with self.assertRaises(RuntimeError):
                nova_win_ps.run("Get-Date")


if __name__ == "__main__":
    unittest.main()
