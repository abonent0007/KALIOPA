"""Манифест источников обновлений: разбор, сравнение версий, статусы."""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "tools"))

import check_module_updates as updater  # noqa: E402


class ManifestTests(unittest.TestCase):
    def test_manifest_is_machine_readable(self):
        sources = updater.load_sources()
        self.assertGreaterEqual(len(sources["modules"]), 15)
        ids = {module["id"] for module in sources["modules"]}
        for required in ("winws", "winws2", "xray-core", "quic-go", "opera-proxy", "python", "rust"):
            self.assertIn(required, ids)

    def test_current_transport_versions_are_recorded(self):
        modules = {module["id"]: module for module in updater.load_sources()["modules"]}
        self.assertEqual("26.10.31", modules["xray-core"]["current"])
        self.assertEqual("0.65.0", modules["quic-go"]["current"])
        self.assertEqual("1.31.0", modules["opera-proxy"]["current"])


class VersionTests(unittest.TestCase):
    def test_numeric_versions_compare_by_parts(self):
        self.assertTrue(updater.is_newer("v26.10.31", "26.10.21"))
        self.assertTrue(updater.is_newer("0.65.0", "0.61.0"))
        self.assertFalse(updater.is_newer("1.44.2", "1.44.2"))

    def test_missing_v_prefix_is_ignored(self):
        self.assertFalse(updater.is_newer("v1.31.0", "1.31.0"))

    def test_non_numeric_falls_back_to_text(self):
        self.assertTrue(updater.is_newer("1.0.13-dev", "1.0.12"))
        self.assertEqual(("local",), updater.version_key("local"))


class StatusTests(unittest.TestCase):
    def test_update_and_current_statuses(self):
        self.assertEqual("update", updater._evaluate("x", {"current": "1.0.0"}, "1.1.0")["status"])
        self.assertEqual("current", updater._evaluate("x", {"current": "1.1.0"}, "1.1.0")["status"])
        self.assertEqual("manual", updater.check_module(
            {"id": "tor", "kind": "manual", "current": "0.4.9.12"}, "", {}, 3600, False)["status"])

    def test_newer_local_build_is_not_reported_as_update(self):
        self.assertEqual("newer-local", updater._evaluate("x", {"current": "2.0.0"}, "1.0.0")["status"])


if __name__ == "__main__":
    unittest.main()
