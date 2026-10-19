import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_local_direct as local  # noqa: E402


class LocalDirectTests(unittest.TestCase):
    def test_russian_tlds_match(self):
        for host in (
            "example.ru", "example.su", "example.рф", "example.xn--p1ai",
            "example.москва", "example.xn--80adxhks", "example.moscow",
            "example.рус", "example.xn--p1acf", "example.дети",
            "example.xn--d1acj3b", "example.tatar",
        ):
            self.assertTrue(local.is_local_direct(host), host)

    def test_foreign_and_lookalike_hosts_do_not_match(self):
        for host in (
            "example.com", "example.by", "example.kz", "example.ua",
            "ru.example.com", "notru", "example.ru.evil.com",
        ):
            self.assertFalse(local.is_local_direct(host), host)

    def test_env_extension_is_normalized(self):
        tlds = local.local_direct_tlds({"NOVA_LOCAL_DIRECT_TLDS": ".by, .қаз, .РФ"})
        self.assertIn(".by", tlds)
        self.assertIn(".xn--80ao21a", tlds)
        self.assertIn(".xn--p1ai", tlds)
        self.assertTrue(local.is_local_direct("example.by", tlds))


if __name__ == "__main__":
    unittest.main()
