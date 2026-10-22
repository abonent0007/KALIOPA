import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_dns_cache as dns_cache  # noqa: E402


class DNSCacheTests(unittest.TestCase):
    def test_positive_result_is_cached(self):
        calls = []
        cache = dns_cache.DNSCache(ttl=300)

        def resolver(domain):
            calls.append(domain)
            return [("ipv4", "93.184.216.34")]

        self.assertEqual(cache.resolve("example.com", resolver, 1000.0), ("93.184.216.34", "ok"))
        self.assertEqual(cache.resolve("example.com", resolver, 1001.0), ("93.184.216.34", "cached_ok"))
        self.assertEqual(calls, ["example.com"])

    def test_ttl_expiry_refreshes(self):
        calls = []
        cache = dns_cache.DNSCache(ttl=300)
        resolver = lambda domain: calls.append(domain) or [("ipv4", "1.1.1.1")]
        cache.resolve("example.com", resolver, 1000.0)
        cache.resolve("example.com", resolver, 1301.0)
        self.assertEqual(calls, ["example.com", "example.com"])

    def test_negative_result_uses_short_ttl(self):
        calls = []
        cache = dns_cache.DNSCache(negative_ttl=60)

        def resolver(domain):
            calls.append(domain)
            raise socket.gaierror("not found")

        self.assertEqual(cache.resolve("missing.test", resolver, 1000.0), (None, "no_dns"))
        self.assertEqual(cache.resolve("missing.test", resolver, 1030.0), (None, "cached_no_dns"))
        self.assertEqual(cache.resolve("missing.test", resolver, 1061.0), (None, "no_dns"))
        self.assertEqual(calls, ["missing.test", "missing.test"])

    def test_ipv4_preferred_over_ipv6(self):
        self.assertEqual(
            dns_cache.choose_ip([("ipv6", "2001:db8::1"), ("ipv4", "192.0.2.1")]),
            "192.0.2.1",
        )

    def test_ipv6_used_when_only_ipv6(self):
        self.assertEqual(dns_cache.choose_ip([("ipv6", "2001:db8::1")]), "2001:db8::1")

    def test_old_24h_entry_without_expiry_is_not_fresh(self):
        cache = dns_cache.DNSCache(ttl=300)
        cache.data["example.com"] = {"ip": "1.1.1.1", "timestamp": 100.0}
        self.assertIsNone(cache.get("example.com", 1000.0))

    def test_use_cache_false_bypasses_lookup(self):
        calls = []
        cache = dns_cache.DNSCache()
        resolver = lambda domain: calls.append(domain) or [("ipv4", "1.1.1.1")]
        cache.resolve("example.com", resolver, 1000.0)
        cache.resolve("example.com", resolver, 1001.0, use_cache=False)
        self.assertEqual(calls, ["example.com", "example.com"])


if __name__ == "__main__":
    unittest.main()
