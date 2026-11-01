"""Личность релея: версия логина берётся из ключа, а не из версии форка.

Релей проверяет `nova-pc-<version>` вместе с `profiles/opera_relay.key`. Ключ
выпускается под конкретную версию, поэтому продуктовый `CURRENT_VERSION` для
логина не годится: после бампа форка релей отвечает 407. Тесты фиксируют, что
`nova.pyw` больше не содержит зашитой версии, а модуль выбирает ту, которую
ключ реально принимает.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parents[1]
NOVA_PY = (BASE_DIR / "nova.pyw").read_text(encoding="utf-8", errors="ignore")
sys.path.insert(0, str(BASE_DIR / "resources"))

import nova_relay_identity as relay_id  # noqa: E402


class SourceTests(unittest.TestCase):
    def test_login_uses_dynamic_identity(self):
        start = NOVA_PY.find("def api_relay_user(")
        self.assertGreater(start, 0, "api_relay_user не найден")
        body = NOVA_PY[start : start + 1400]
        self.assertIn("nova_relay_identity.current_version", body)
        self.assertNotIn("API_RELAY_KEY_VERSION", body)
        self.assertNotIn('globals().get("CURRENT_VERSION"', body)

    def test_no_pinned_relay_version_left(self):
        self.assertNotRegex(NOVA_PY, r'API_RELAY_KEY_VERSION\s*=\s*"[^"]+"')

    def test_identity_module_is_shipped(self):
        self.assertTrue((BASE_DIR / "resources" / "nova_relay_identity.py").is_file())


class VersionSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "profiles").mkdir(parents=True, exist_ok=True)
        (self.base / "temp").mkdir(parents=True, exist_ok=True)
        (self.base / "profiles" / "opera_relay.key").write_text("secret-key", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_environment_override_wins(self):
        version = relay_id.current_version(self.base, environ={"NOVA_RELAY_KEY_VERSION": "1.50.0"})
        self.assertEqual("1.50.0", version)

    def test_cache_is_used_only_for_the_same_key(self):
        relay_id.save_cache(self.base, {
            "version": "1.44.1",
            "key_sha256": relay_id.key_fingerprint("secret-key"),
        })
        self.assertEqual("1.44.1", relay_id.current_version(self.base, environ={}))
        relay_id.save_cache(self.base, {
            "version": "1.44.1",
            "key_sha256": relay_id.key_fingerprint("another-key"),
        })
        self.assertEqual(relay_id.DEFAULT_VERSION, relay_id.current_version(self.base, environ={}))

    def test_marker_is_the_next_fallback(self):
        relay_id.write_marker(self.base, "1.43.2")
        self.assertEqual("1.43.2", relay_id.current_version(self.base, environ={}))

    def test_candidates_are_deduplicated_and_ordered(self):
        versions = relay_id.candidate_versions(self.base, "1.44.2", ["1.44.2", "1.44.1"])
        self.assertEqual("1.44.2", versions[0])
        self.assertEqual("1.44.1", versions[1])
        self.assertEqual(len(versions), len(set(versions)))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "profiles").mkdir(parents=True, exist_ok=True)
        (self.base / "profiles" / "opera_relay.key").write_text("secret-key", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _fetcher(url, timeout=None):
        if "version.json" in url:
            return '{"version": "1.44.2"}'
        return "<entry><title>v1.44.2</title></entry><entry><title>v1.44.1</title></entry>"

    def test_first_accepted_version_is_cached_and_marked(self):
        def prober(version):
            return "ok" if version == "1.44.1" else "auth"

        result = relay_id.resolve(self.base, prober=prober, fetcher=self._fetcher)
        self.assertTrue(result["verified"])
        self.assertEqual("1.44.1", result["version"])
        self.assertEqual("1.44.1", relay_id.read_marker(self.base))
        self.assertEqual("1.44.1", relay_id.current_version(self.base, environ={}))

    def test_unreachable_relay_keeps_the_cached_version(self):
        relay_id.write_marker(self.base, "1.43.2")
        result = relay_id.resolve(self.base, prober=lambda version: "unreachable", fetcher=self._fetcher)
        self.assertFalse(result["verified"])
        self.assertEqual("unreachable", result["reason"])
        self.assertEqual("1.43.2", result["version"])

    def test_missing_key_is_reported_without_probing(self):
        (self.base / "profiles" / "opera_relay.key").unlink()
        result = relay_id.resolve(self.base, prober=mock.Mock(side_effect=AssertionError("probe called")))
        self.assertEqual("no-key", result["reason"])


if __name__ == "__main__":
    unittest.main()
