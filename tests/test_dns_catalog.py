"""Каталог DNS-резолверов и назначение резолвера маршруту."""

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_dns_catalog as catalog  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_catalog_has_public_and_community_resolvers(self):
        rows = catalog.resolvers()
        ids = {row["id"] for row in rows}
        self.assertIn("cf", ids)
        self.assertIn("google", ids)
        self.assertIn("comss", ids)
        community = {row["id"] for row in rows if row.get("community")}
        self.assertIn("geohide", community)
        self.assertNotIn("cf", community)

    def test_geohide_gets_fresh_addresses_when_given(self):
        rows = {row["id"]: row for row in catalog.resolvers(["192.0.2.10"])}
        self.assertEqual(["192.0.2.10"], rows["geohide"]["ips"])


class CheckTests(unittest.TestCase):
    def test_ok_result_reports_the_fastest_answer(self):
        calls = []

        def query(server, timeout):
            calls.append((server, timeout))
            return True if server == "1.1.1.1" else None

        row = {"id": "cf", "title": "Cloudflare", "host": "1.1.1.1",
               "ips": ["1.1.1.1", "1.0.0.1"], "community": False, "note": ""}
        result = catalog.check(row, timeout=1.5, query_fn=query)
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["latency_ms"], int)
        self.assertEqual(["1.1.1.1", "1.0.0.1"], result["ips"])
        self.assertIn(("1.1.1.1", 1.5), calls)

    def test_dead_resolver_reports_an_error(self):
        result = catalog.check({"id": "x", "host": "127.0.0.1", "ips": ["127.0.0.1"]},
                               timeout=0.3,
                               query_fn=lambda server, timeout: None)
        self.assertFalse(result["ok"])
        self.assertIn("нет ответа", result["error"])

    def test_unresolvable_host_is_an_error(self):
        result = catalog.check({"id": "x", "host": "no-such-host.invalid", "ips": []},
                               query_fn=lambda server, timeout: True)
        self.assertFalse(result["ok"])
        self.assertEqual([], result["ips"])

    def test_check_many_covers_every_row(self):
        out = catalog.check_many(catalog.resolvers(), query_fn=lambda server, timeout: True)
        self.assertEqual(len(catalog.resolvers()), len(out))

    def test_domain_is_resolved_dynamically_first(self):
        row = {"id": "x", "host": "dns.example", "ips": ["192.0.2.9"],
               "community": False, "note": ""}
        fake = [(None, None, None, None, ("192.0.2.50", 0))]
        with mock.patch.object(catalog.socket, "getaddrinfo", return_value=fake):
            self.assertEqual(["192.0.2.50"], catalog.addresses_of(row))

    def test_static_addresses_are_the_fallback(self):
        row = {"id": "x", "host": "dns.example", "ips": ["192.0.2.9"],
               "community": False, "note": ""}
        with mock.patch.object(catalog.socket, "getaddrinfo", side_effect=OSError()):
            self.assertEqual(["192.0.2.9"], catalog.addresses_of(row))


class RoutesTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="kaliopa-dns-routes-")

    def test_unknown_routes_are_dropped(self):
        data = catalog.normalize_routes({"default": "cf", "routes": {"ru": "geohide",
                                                                     "bogus": "cf"}})
        self.assertEqual("geohide", data["routes"]["ru"])
        self.assertNotIn("bogus", data["routes"])
        for route, _title in catalog.ROUTE_ORDER:
            self.assertIn(route, data["routes"])

    def test_roundtrip(self):
        catalog.save_routes(self.base, {"default": "cf", "routes": {"ai_apps": "comss"}})
        loaded = catalog.load_routes(self.base)
        self.assertEqual("comss", loaded["routes"]["ai_apps"])
        self.assertEqual("", loaded["routes"]["ru"])

    def test_missing_file_is_empty_assignment(self):
        data = catalog.load_routes(self.base)
        self.assertEqual("cf", data["default"])
        self.assertTrue(all(not value for value in data["routes"].values()))


if __name__ == "__main__":
    unittest.main()
