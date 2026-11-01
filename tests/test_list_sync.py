"""Сценарии обновления списков: сеть, sha256, устаревшее зеркало, путь.

`sync_from_network` принимает `fetch` — это позволяет проверить механизм
обновления без сети и зафиксировать правила, на которых он держится:
проверка sha256, отказ от устаревшего манифеста, атомарная запись и фильтр
путей (`list/*.txt`, без `..` и без `u_*`).
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_list_sync as list_sync  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ListSyncTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        (self.base / "list").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _manifest(self, files, generated=100):
        return json.dumps({"schema": 1, "generated": generated, "files": files}).encode()

    def _sync(self, manifest, bodies, state_path=None):
        def fetch(url, proxies=(), expect_sha256=None, **kwargs):
            if url.endswith(list_sync.MANIFEST_NAME):
                return manifest
            for rel, body in bodies.items():
                if rel in url:
                    if expect_sha256 and sha256(body) != expect_sha256:
                        return None
                    return body
            return None

        return list_sync.sync_from_network(
            str(self.base), fetch=fetch, log=lambda _msg: None, state_path=state_path
        )

    def test_matching_sha_updates_file_and_state(self):
        body = b"example.com\n# comment\n"
        result = self._sync(
            self._manifest({"list/ai.txt": {"sha256": sha256(body)}}),
            {"list/ai.txt": body},
        )

        self.assertEqual(["list/ai.txt"], result["updated"])
        self.assertEqual([], result["failed"])
        self.assertEqual(body, (self.base / "list" / "ai.txt").read_bytes())
        state = json.loads((self.base / "temp" / "list_sync_state.json").read_text(encoding="utf-8"))
        self.assertEqual(100, state["generated"])

    def test_sha_mismatch_is_failure_and_keeps_old_file(self):
        old = b"old.example\n"
        (self.base / "list" / "ai.txt").write_bytes(old)
        # Манифест ждёт один файл, зеркало отдаёт другой: fetch_bytes отсеивает
        # его по sha256 и возвращает None, локальная копия остаётся прежней.
        manifest = self._manifest({"list/ai.txt": {"sha256": sha256(b"expected.example\n")}})

        result = self._sync(manifest, {"list/ai.txt": b"tampered.example\n"})

        self.assertEqual(["list/ai.txt"], result["failed"])
        self.assertEqual(old, (self.base / "list" / "ai.txt").read_bytes())
        self.assertFalse((self.base / "temp" / "list_sync_state.json").exists())

    def test_stale_manifest_is_skipped(self):
        state = self.base / "state.json"
        state.write_text(json.dumps({"generated": 200}), encoding="utf-8")
        manifest = self._manifest({"list/ai.txt": {"sha256": sha256(b"x.example\n")}}, generated=100)

        result = self._sync(manifest, {"list/ai.txt": b"x.example\n"}, state_path=str(state))

        self.assertEqual({"skipped": "stale"}, result)
        self.assertFalse((self.base / "list" / "ai.txt").exists())

    def test_traversal_and_foreign_dirs_are_ignored(self):
        body = b"ok.example\n"
        manifest = self._manifest(
            {
                "list/../evil.txt": {"sha256": sha256(body)},
                "ip/main.txt": {"sha256": sha256(body)},
                "list/u_hidden.txt": {"sha256": sha256(body)},
                "list/ai.txt": {"sha256": sha256(body)},
            }
        )

        result = self._sync(manifest, {"list/ai.txt": body, "evil.txt": body, "ip/main.txt": body})

        self.assertEqual(["list/ai.txt"], result["updated"])
        self.assertFalse((self.base.parent / "evil.txt").exists())
        self.assertFalse((self.base / "ip").exists())

    def test_comment_only_body_is_rejected(self):
        body = b"# only a header\n\n"
        result = self._sync(
            self._manifest({"list/ai.txt": {"sha256": sha256(body)}}),
            {"list/ai.txt": body},
        )

        self.assertEqual(["list/ai.txt"], result["failed"])
        self.assertFalse((self.base / "list" / "ai.txt").exists())

    def test_broken_manifest_returns_error(self):
        result = self._sync(b"{not json", {})

        self.assertEqual({"error": "manifest"}, result)


if __name__ == "__main__":
    unittest.main()
