"""Гигиена процессов: осиротевшие winws_test старше порога снимаются."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_process_hygiene as hygiene  # noqa: E402


class _Runner:
    def __init__(self, output="", fail=False):
        self.output = output
        self.fail = fail
        self.commands = []

    def __call__(self, command, timeout=None):
        self.commands.append(command)
        if self.fail:
            raise RuntimeError("powershell failed")
        return self.output


class OrphanTests(unittest.TestCase):
    def test_only_processes_older_than_the_threshold_are_returned(self):
        output = json.dumps([
            {"ProcessId": 10, "Name": "winws_test.exe", "AgeSec": 120},
            {"ProcessId": 11, "Name": "winws_test.exe", "AgeSec": 3600},
        ])
        rows = hygiene.find_orphans(max_age_sec=600, runner=_Runner(output))
        self.assertEqual([{"pid": 11, "name": "winws_test.exe", "age_sec": 3600}], rows)

    def test_a_single_row_is_accepted(self):
        output = json.dumps({"ProcessId": 7, "Name": "winws_test.exe", "AgeSec": 900})
        rows = hygiene.find_orphans(max_age_sec=600, runner=_Runner(output))
        self.assertEqual([7], [row["pid"] for row in rows])

    def test_empty_output_means_no_orphans(self):
        self.assertEqual([], hygiene.find_orphans(runner=_Runner("")))

    def test_unsafe_process_names_are_ignored(self):
        self.assertEqual([], hygiene.find_orphans(names=("x'; Remove-Item C:\\",), runner=_Runner("[]")))

    def test_kill_reports_the_number_and_uses_the_runner(self):
        output = json.dumps([
            {"ProcessId": 10, "Name": "winws_test.exe", "AgeSec": 3600},
            {"ProcessId": 11, "Name": "winws_test.exe", "AgeSec": 7200},
        ])
        runner = _Runner(output)
        killed = hygiene.kill_orphans(max_age_sec=600, runner=runner)
        self.assertEqual(2, killed)
        self.assertTrue(any("Stop-Process -Id 10" in command for command in runner.commands))
        self.assertTrue(any("Stop-Process -Id 11" in command for command in runner.commands))

    def test_a_failed_listing_is_reported_not_raised(self):
        messages = []
        killed = hygiene.kill_orphans(runner=_Runner(fail=True), log=messages.append)
        self.assertEqual(0, killed)
        self.assertTrue(messages)


if __name__ == "__main__":
    unittest.main()
