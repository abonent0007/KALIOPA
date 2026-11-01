"""Снимок DNS-адаптеров и служба локального DoH: восстановление и откат."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_dns_adapters as adapters  # noqa: E402
import nova_doh_service as service  # noqa: E402


class _Runner:
    def __init__(self, output=""):
        self.output = output
        self.commands = []

    def __call__(self, command, timeout=None):
        self.commands.append(command)
        return self.output


class AdapterSnapshotTests(unittest.TestCase):
    def test_single_adapter_json_is_normalised(self):
        runner = _Runner(json.dumps({
            "InterfaceIndex": 18,
            "InterfaceAlias": "Wi-Fi",
            "ServerAddresses": ["10.0.0.1"],
        }))
        rows = adapters.snapshot(runner=runner)
        self.assertEqual([{"index": 18, "alias": "Wi-Fi", "servers": ["10.0.0.1"]}], rows)

    def test_empty_output_is_an_empty_snapshot(self):
        self.assertEqual([], adapters.snapshot(runner=_Runner("")))

    def test_apply_and_restore_commands(self):
        runner = _Runner()
        rows = [{"index": 18, "alias": "Wi-Fi", "servers": ["10.0.0.1"]}]
        self.assertEqual(1, adapters.apply(rows, "127.0.0.1", runner=runner))
        self.assertIn("-InterfaceIndex 18 -ServerAddresses @('127.0.0.1')", runner.commands[0])
        self.assertEqual(1, adapters.restore(rows, runner=runner))
        self.assertIn("-InterfaceIndex 18 -ServerAddresses @('10.0.0.1')", runner.commands[1])

    def test_empty_server_list_resets_the_adapter(self):
        runner = _Runner()
        adapters.restore([{"index": 7, "servers": []}], runner=runner)
        self.assertIn("-ResetServerAddresses", runner.commands[0])

    def test_non_ip_address_is_refused(self):
        with self.assertRaises(ValueError):
            adapters.apply([{"index": 1, "servers": []}], "127.0.0.1; rm -rf", runner=_Runner())

    def test_save_and_restore_file_removes_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, adapters.SNAPSHOT_FILENAME)
            adapters.save(path, [{"index": 3, "alias": "eth", "servers": ["1.1.1.1"]}])
            self.assertTrue(os.path.exists(path))
            runner = _Runner()
            self.assertTrue(adapters.restore_file(path, runner=runner))
            self.assertFalse(os.path.exists(path))
            self.assertIn("1.1.1.1", runner.commands[0])
            self.assertFalse(adapters.restore_file(path, runner=runner))


class _FakeAdapters:
    def __init__(self, fail_apply=False):
        self.rows = [{"index": 18, "alias": "Wi-Fi", "servers": ["10.0.0.1"]}]
        self.fail_apply = fail_apply
        self.saved = None
        self.applied = None
        self.restored = None
        self.recovered = False

    def snapshot(self):
        return list(self.rows)

    def save(self, path, rows):
        self.saved = (path, rows)

    def apply(self, rows, dns_ip):
        if self.fail_apply:
            raise RuntimeError("set failed")
        self.applied = (rows, dns_ip)
        return len(rows)

    def restore(self, rows):
        self.restored = rows
        return len(rows)

    def recover(self, temp_dir):
        self.recovered = True
        return True


class _FakeResolver:
    def __init__(self, upstream=None):
        self.upstream = upstream
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class DohServiceTests(unittest.TestCase):
    def setUp(self):
        service._resolver = None

    def tearDown(self):
        service._resolver = None

    def test_start_applies_dns_and_keeps_the_original_as_fallback(self):
        fake = _FakeAdapters()
        created = []

        def factory(upstream=None):
            created.append(_FakeResolver(upstream))
            return created[-1]

        with tempfile.TemporaryDirectory() as tmp:
            ok = service.start(tmp, adapters=fake, resolver_factory=factory)
            self.assertTrue(ok)
            self.assertEqual(("127.0.0.1",), (fake.applied[1],))
            self.assertEqual("10.0.0.1:53", created[0].upstream)
            self.assertTrue(created[0].started)
            self.assertIsNotNone(fake.saved)
            self.assertEqual(service.snapshot_path(tmp), fake.saved[0])

    def test_failed_apply_rolls_the_snapshot_back(self):
        fake = _FakeAdapters(fail_apply=True)
        created = []

        def factory(upstream=None):
            created.append(_FakeResolver(upstream))
            return created[-1]

        with tempfile.TemporaryDirectory() as tmp:
            ok = service.start(tmp, adapters=fake, resolver_factory=factory)
            self.assertFalse(ok)
            self.assertEqual(fake.rows, fake.restored)
            self.assertTrue(created[0].stopped)
            self.assertFalse(os.path.exists(service.snapshot_path(tmp)))
            self.assertIsNone(service._resolver)

    def test_stop_restores_from_the_snapshot_file(self):
        fake = _FakeAdapters()
        with tempfile.TemporaryDirectory() as tmp:
            service.start(tmp, adapters=fake, resolver_factory=lambda upstream=None: _FakeResolver(upstream))
            service.stop(tmp, adapters=fake)
            self.assertTrue(fake.recovered)
            self.assertIsNone(service._resolver)

    def test_recover_reports_a_snapshot_from_a_previous_run(self):
        fake = _FakeAdapters()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(service.recover(tmp, adapters=fake))
            self.assertTrue(fake.recovered)


if __name__ == "__main__":
    unittest.main()
