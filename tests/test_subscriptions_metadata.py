"""Подписка: заголовки/метаданные сохраняются в реестре и видны в строке.

Проверяем три вещи, которых раньше не было:
* 304 тоже обновляет `Subscription-Userinfo` (трафик меняется без тела);
* старые записи без `provider` читаются, а новые поля переживают `normalize`;
* строка окна показывает остаток/срок и не врёт про «безлимит».
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_profiles_ui as ui  # noqa: E402
import nova_subscriptions as subs  # noqa: E402


def record(**overrides):
    base = {
        "id": "sub-1",
        "url": "https://example.com/sub",
        "name": "",
        "kind": "vless",
        "enabled": True,
        "interval_hours": 12,
        "keep": 10,
        "shape": subs._SHAPE,
        "node_count": 3,
        "last_status": "состав не изменился",
        "provider": {},
        "last_stats": {},
    }
    base.update(overrides)
    return subs.normalize_record(base)


class FetchHeaderTests(unittest.TestCase):
    class Response:
        def __init__(self, status=200, body=b"vless://example"):
            self.status_code = status
            self.headers = {"ETag": '"v1"',
                            "Subscription-Userinfo": "upload=1; download=2; total=3",
                            "Profile-Title": "Panel"}
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_content(self, chunk_size=0):
            yield self._body

    class Session:
        def __init__(self, response):
            self.response = response

        def get(self, *args, **kwargs):
            return self.response

        def close(self):
            pass

    def test_200_keeps_metadata_headers(self):
        result = subs.fetch("https://example.com/sub",
                            session_factory=lambda _route: self.Session(self.Response()))
        self.assertEqual("ok", result.status)
        self.assertEqual("Panel", result.headers.get("Profile-Title"))
        self.assertEqual("upload=1; download=2; total=3",
                         result.headers.get("Subscription-Userinfo"))

    def test_304_keeps_metadata_headers(self):
        result = subs.fetch("https://example.com/sub",
                            session_factory=lambda _route: self.Session(
                                self.Response(status=304, body=b"")))
        self.assertEqual("not_modified", result.status)
        self.assertEqual("Panel", result.headers.get("Profile-Title"))


class RefreshMetadataTests(unittest.TestCase):
    def test_304_updates_provider_without_a_body(self):
        base = tempfile.mkdtemp(prefix="kaliopa-subs-")
        before = record(provider={"title": "Old", "userinfo": {"total": 100}})
        result = subs.FetchResult("not_modified", headers={
            "Subscription-Userinfo": "upload=10; download=20; total=1000; expire=1893456000",
            "Profile-Title": "New provider",
            "Profile-Update-Interval": "6",
        })
        outcome, after, stats = subs.refresh(
            base, before, fetcher=lambda *args, **kwargs: result, now=1000)
        self.assertEqual("unchanged", outcome)
        self.assertEqual({}, stats)
        self.assertEqual("New provider", after["provider"]["title"])
        self.assertEqual(1000, after["provider"]["userinfo"]["total"])
        self.assertEqual(6, after["provider"]["update_interval_hours"])
        self.assertEqual(1000, after["provider"]["updated_at"])

    def test_body_metadata_is_used_when_headers_are_absent(self):
        base = tempfile.mkdtemp(prefix="kaliopa-subs-")
        body = (b"#profile-title: Body provider\n"
                b"#subscription-userinfo: upload=1; download=2; total=0; expire=0\n"
                b"#profile-update-interval: 24\n")
        result = subs.FetchResult("ok", body=body, size=len(body))
        outcome, after, stats = subs.refresh(
            base, record(), fetcher=lambda *args, **kwargs: result, now=2000)
        self.assertEqual("empty", outcome)
        self.assertEqual("Body provider", after["provider"]["title"])
        self.assertEqual(0, after["provider"]["userinfo"]["total"])
        self.assertEqual(24, after["provider"]["update_interval_hours"])
        self.assertEqual("в ответе нет Xray-ссылок (vless/trojan/vmess/ss)", after["last_status"])

    def test_headers_win_over_body(self):
        base = tempfile.mkdtemp(prefix="kaliopa-subs-")
        body = b"#profile-title: Body\n"
        result = subs.FetchResult("ok", body=body, size=len(body),
                                  headers={"Profile-Title": "Header"})
        _outcome, after, _stats = subs.refresh(
            base, record(), fetcher=lambda *args, **kwargs: result, now=3000)
        self.assertEqual("Header", after["provider"]["title"])


class RecordShapeTests(unittest.TestCase):
    def test_old_record_gets_empty_metadata(self):
        old = {"url": "https://example.com/sub", "shape": subs._SHAPE}
        normalized = subs.normalize_record(old)
        self.assertEqual({}, normalized["provider"])
        self.assertEqual({}, normalized["last_stats"])

    def test_metadata_survives_normalization(self):
        before = record(provider={"title": "Provider",
                                  "userinfo": {"total": 10, "upload": 2}},
                        last_stats={"other_scheme": 4, "xray_json": 2})
        after = subs.normalize_record(before)
        self.assertEqual("Provider", after["provider"]["title"])
        self.assertEqual(4, after["last_stats"]["other_scheme"])
        self.assertEqual(2, after["last_stats"]["xray_json"])


class SubscriptionRowTests(unittest.TestCase):
    def test_provider_title_and_remaining_traffic(self):
        text, tone = ui.format_subscription_row(record(
            provider={"title": "Provider",
                      "userinfo": {"upload": 100, "download": 200, "total": 1000,
                                   "expire": int(time.time()) + 86400}},
            last_stats={"other_scheme": 5},
        ), now=time.time())
        self.assertIn("Provider", text)
        self.assertIn("осталось", text)
        self.assertIn("чужих ссылок: 5", text)
        self.assertNotEqual("fail", tone)

    def test_exhausted_and_expired_is_fail(self):
        now = int(time.time())
        text, tone = ui.format_subscription_row(record(
            provider={"userinfo": {"upload": 60, "download": 40, "total": 100,
                                   "expire": now - 10}},
        ), now=now)
        self.assertIn("трафик исчерпан", text)
        self.assertIn("истёк", text)
        self.assertEqual("fail", tone)

    def test_missing_total_is_not_unlimited(self):
        text, _tone = ui.format_subscription_row(record(
            provider={"userinfo": {"expire": int(time.time()) + 86400}},
        ), now=time.time())
        self.assertNotIn("безлимит", text)


if __name__ == "__main__":
    unittest.main()
