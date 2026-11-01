"""GeoHide: адреса берутся из hosts-файла сервиса, а зашитый список — только fallback.

Сервис публикует свои адреса в шапке hosts-файла («Эти IP-адреса принадлежат GeoHide DNS»).
Тест держит разбор этой шапки, запись кэша, отказ от мусора и поведение без сети.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_dns_endpoints as endpoints  # noqa: E402

SAMPLE = """### geohide.ru: hosts file
# Последнее обновление: 20.10.2026 04:56:02
# Регион серверов: RU
# Эти IP-адреса принадлежат GeoHide DNS:
# 159.194.200.33
# 193.233.112.67
# 193.233.112.68
# 5.175.161.3
# Остальные IP-адреса принадлежат сторонним сервисам.
1.2.3.4 example.com
""".replace("принадлежат GeoHide DNS", "GeoHide DNS")


class ParseTests(unittest.TestCase):
    def test_parses_header_block_only(self):
        self.assertEqual(
            ("159.194.200.33", "193.233.112.67", "193.233.112.68", "5.175.161.3"),
            endpoints.parse_servers(SAMPLE),
        )

    def test_ignores_hosts_mappings_below_block(self):
        self.assertNotIn("1.2.3.4", endpoints.parse_servers(SAMPLE))

    def test_rejects_non_global_addresses(self):
        text = "# GeoHide DNS\n# 127.0.0.1\n# 8.8.8.8\n"
        self.assertEqual(("8.8.8.8",), endpoints.parse_servers(text))

    def test_update_date_is_read(self):
        self.assertEqual("20.10.2026 04:56:02", endpoints.parse_update_date(SAMPLE))

    def test_missing_marker_gives_empty(self):
        self.assertEqual((), endpoints.parse_servers("1.2.3.4 example.com\n"))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        (self.base / "temp").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_refresh_writes_cache(self):
        result = endpoints.refresh(str(self.base), fetch=lambda url: SAMPLE)
        self.assertTrue(result["ok"])
        self.assertEqual(4, result["count"])
        servers, updated_at = endpoints.read_cache(str(self.base))
        self.assertEqual(("159.194.200.33", "193.233.112.68", "193.233.112.67", "5.175.161.3"), servers)
        self.assertGreater(updated_at, 0)

    def test_refresh_without_network_keeps_old_cache(self):
        endpoints.refresh(str(self.base), fetch=lambda url: SAMPLE)

        def broken(url):
            raise OSError("offline")

        result = endpoints.refresh(str(self.base), fetch=broken)
        self.assertFalse(result["ok"])
        servers, _ = endpoints.read_cache(str(self.base))
        self.assertEqual(4, len(servers))

    def test_startup_uses_cache(self):
        endpoints.refresh(str(self.base), fetch=lambda url: SAMPLE)
        with mock.patch.dict("os.environ", {"NOVA_DNS_ENDPOINTS_AUTO": "0"}):
            servers = endpoints.servers_for_startup(str(self.base))
        self.assertEqual(("159.194.200.33", "193.233.112.68", "193.233.112.67", "5.175.161.3"), servers)

    def test_startup_without_cache_falls_back(self):
        with mock.patch.dict("os.environ", {"NOVA_DNS_ENDPOINTS_AUTO": "0"}):
            servers = endpoints.servers_for_startup(str(self.base))
        self.assertEqual(endpoints.order_servers(endpoints.FALLBACK_SERVERS)[: endpoints.MAX_SERVERS], servers)

    def test_refresh_merges_sources_and_caps(self):
        many = SAMPLE.replace("# 5.175.161.3", "\n".join(f"# 11.0.0.{i}" for i in range(1, 20)))
        result = endpoints.refresh(str(self.base), fetch=lambda url: many)
        self.assertTrue(result["ok"])
        self.assertEqual(endpoints.MAX_SERVERS, result["count"])


if __name__ == "__main__":
    unittest.main()
