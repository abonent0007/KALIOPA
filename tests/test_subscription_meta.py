"""Метаданные подписки: `Subscription-Userinfo`, `Profile-*` и `#`-строки.

3x-ui и большинство панелей отдают трафик/срок в заголовках, а часть
провайдеров повторяет их в теле. Парсер обязан не путать «total отсутствует»
с «total=0» (безлимит), понимать `base64:` у названия и не пропускать
javascript-ссылки в `Support-Url`.
"""

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_subscription_meta as meta  # noqa: E402


class UserinfoTests(unittest.TestCase):
    def test_3xui_header(self):
        info = meta.parse_userinfo("upload=1024; download=2048; total=10485760; expire=1893456000")
        self.assertEqual({"upload": 1024, "download": 2048, "total": 10485760,
                          "expire": 1893456000}, info)

    def test_missing_total_is_not_unlimited(self):
        info = meta.parse_userinfo("expire=1893456000")
        self.assertEqual({"expire": 1893456000}, info)
        self.assertNotIn("total", info)

    def test_milliseconds_become_seconds(self):
        info = meta.parse_userinfo("total=10; expire=1893456000000")
        self.assertEqual(1893456000, info["expire"])

    def test_garbage_is_ignored(self):
        self.assertIsNone(meta.parse_userinfo(""))
        self.assertIsNone(meta.parse_userinfo("not a userinfo"))

    def test_negative_and_huge_values_are_clamped(self):
        info = meta.parse_userinfo("upload=-5; download=999999999999999999999999")
        self.assertEqual(0, info["upload"])
        self.assertEqual(meta.MAX_BYTES, info["download"])


class TitleTests(unittest.TestCase):
    def test_raw_title(self):
        self.assertEqual("My provider", meta.decode_profile_title("My provider"))

    def test_base64_title(self):
        encoded = base64.b64encode("Провайдер".encode("utf-8")).decode("ascii")
        self.assertEqual("Провайдер", meta.decode_profile_title("base64:" + encoded))

    def test_broken_base64_falls_back_to_text(self):
        self.assertEqual("base64:not-base64!", meta.decode_profile_title("base64:not-base64!"))


class HeaderAndBodyTests(unittest.TestCase):
    def test_headers_are_case_insensitive(self):
        provider = meta.parse_headers({
            "subscription-userinfo": "upload=1; download=2; total=3; expire=4",
            "profile-title": "Panel",
            "profile-update-interval": "6",
            "support-url": "https://example.com/help",
        })
        self.assertEqual("Panel", provider["title"])
        self.assertEqual(6, provider["update_interval_hours"])
        self.assertEqual({"upload": 1, "download": 2, "total": 3, "expire": 4},
                         provider["userinfo"])
        self.assertEqual("https://example.com/help", provider["support_url"])

    def test_body_metadata(self):
        provider = meta.parse_body_metadata(
            "#profile-title: Body provider\n"
            "#profile-update-interval: 12\n"
            "#subscription-userinfo: upload=1; download=2; total=0; expire=0\n"
            "vless://example\n"
        )
        self.assertEqual("Body provider", provider["title"])
        self.assertEqual(12, provider["update_interval_hours"])
        self.assertEqual(0, provider["userinfo"]["total"])

    def test_javascript_url_is_not_kept(self):
        provider = meta.parse_headers({"Support-Url": "javascript:alert(1)"})
        self.assertNotIn("support_url", provider)

    def test_interval_is_clamped(self):
        self.assertEqual(1, meta.parse_headers({"Profile-Update-Interval": "0"})[
            "update_interval_hours"])
        self.assertEqual(meta.MAX_INTERVAL_HOURS, meta.parse_headers(
            {"Profile-Update-Interval": "9999"})["update_interval_hours"])


class SanitizeAndMergeTests(unittest.TestCase):
    def test_sanitize_rejects_bad_shapes(self):
        self.assertEqual({}, meta.sanitize_provider(None))
        self.assertEqual({}, meta.sanitize_provider("nope"))
        clean = meta.sanitize_provider({
            "title": "x" * 500,
            "update_interval_hours": 9999,
            "support_url": "ftp://example.com",
            "userinfo": {"upload": -1, "total": 10},
        })
        self.assertEqual(meta.MAX_TITLE_CHARS, len(clean["title"]))
        self.assertEqual(meta.MAX_INTERVAL_HOURS, clean["update_interval_hours"])
        self.assertNotIn("support_url", clean)
        self.assertEqual({"upload": 0, "total": 10}, clean["userinfo"])

    def test_merge_keeps_fields_the_new_answer_omits(self):
        old = {"title": "Old", "userinfo": {"upload": 1, "total": 100}, "support_url": "https://a"}
        merged = meta.merge_provider(old, {"userinfo": {"download": 2}}, now=123)
        self.assertEqual("Old", merged["title"])
        self.assertEqual("https://a", merged["support_url"])
        self.assertEqual({"upload": 1, "total": 100, "download": 2}, merged["userinfo"])
        self.assertEqual(123, merged["updated_at"])

    def test_empty_new_answer_does_not_change_anything(self):
        old = {"title": "Old", "userinfo": {"total": 10}}
        self.assertEqual(old, meta.merge_provider(old, {}, now=123))


if __name__ == "__main__":
    unittest.main()
