"""DoH-транспорт DNS-AI: выбор прокси, сравнение ответов, кэш, защитные ветки старта."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_dns_doh as doh  # noqa: E402


class ProxyTests(unittest.TestCase):
    def test_warp_socks_wins_over_the_opera_slot(self):
        self.assertEqual("socks5://127.0.0.1:1370", doh.proxy_url(lambda port: True))

    def test_opera_http_is_the_second_choice(self):
        self.assertEqual("http://127.0.0.1:1371", doh.proxy_url(lambda port: port == 1371))

    def test_no_slot_means_direct(self):
        self.assertEqual("", doh.proxy_url(lambda port: False))


class SupportedNamesTests(unittest.TestCase):
    NAMES = ("chatgpt.com", "gemini.google.com", "example.com")

    def support(self, doh_answers, ref_answers):
        return doh.supported_names(
            self.NAMES,
            reference_fn=lambda name: ref_answers.get(name),
            query_fn=lambda name: doh_answers.get(name),
        )

    def test_only_names_with_a_different_answer_get_a_rule(self):
        got = self.support(
            {"chatgpt.com": ["62.60.230.61"], "gemini.google.com": ["89.169.55.148"],
             "example.com": ["93.184.216.34"]},
            {"chatgpt.com": ["104.18.32.47"], "gemini.google.com": ["142.251.150.2"],
             "example.com": ["93.184.216.34"]},
        )
        self.assertEqual({"chatgpt.com": ["127.0.0.1"], "gemini.google.com": ["127.0.0.1"]}, got)

    def test_a_name_without_doh_answer_is_skipped(self):
        got = self.support({"chatgpt.com": [], "gemini.google.com": None}, {})
        self.assertEqual({}, got)

    def test_an_unknown_reference_still_takes_the_rule(self):
        # The reference resolver may be unreachable; the DoH answer is then the only fact.
        got = self.support({"chatgpt.com": ["62.60.230.61"]}, {})
        self.assertEqual({"chatgpt.com": ["127.0.0.1"]}, got)

    def test_a_reference_equal_to_doh_gets_nothing(self):
        got = self.support({"chatgpt.com": ["62.60.230.61"]}, {"chatgpt.com": ["62.60.230.61"]})
        self.assertEqual({}, got)


class StartGuardTests(unittest.TestCase):
    def test_missing_helper_is_reported(self):
        ok, reason = doh.start("C:/nonexistent/nova-go.exe", None)
        self.assertFalse(ok)
        self.assertIn("не найден", reason)

    def test_an_occupied_port_is_not_fought_over(self):
        base = tempfile.mkdtemp(prefix="doh-start-")
        helper = pathlib.Path(base) / "nova-go.exe"
        helper.write_bytes(b"stub")
        ok, reason = doh.start(str(helper), None, port_open=lambda port: True)
        self.assertFalse(ok)
        self.assertIn("занят", reason)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="doh-cache-")

    def test_roundtrip(self):
        doh.save_cache(self.base, "sig-1", {"chatgpt.com": ["127.0.0.1"]})
        self.assertEqual({"chatgpt.com": ["127.0.0.1"]}, doh.load_cache(self.base, "sig-1"))

    def test_another_signature_is_a_miss(self):
        doh.save_cache(self.base, "sig-1", {"chatgpt.com": ["127.0.0.1"]})
        self.assertIsNone(doh.load_cache(self.base, "sig-2"))

    def test_a_broken_file_is_a_miss(self):
        path = pathlib.Path(self.base) / "temp" / doh.CACHE_FILENAME
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(doh.load_cache(self.base, "sig-1"))

    def test_an_empty_base_dir_writes_nothing(self):
        doh.save_cache("", "sig-1", {"x": ["127.0.0.1"]})
        self.assertIsNone(doh.load_cache("", "sig-1"))


if __name__ == "__main__":
    unittest.main()
