"""Варианты Proton-конфига: до трёх портов и разные junk-наборы, ключи не меняются."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_proton_variants as variants  # noqa: E402

CONF = """[Interface]
PrivateKey = AAAA
Address = 10.2.0.2/32
Jc = 5
Jmin = 59
Jmax = 103
H1 = 1

[Peer]
PublicKey = BBBB
AllowedIPs = 0.0.0.0/0
Endpoint = 194.180.34.9:443
"""


class VariantTests(unittest.TestCase):
    def test_three_variants_with_distinct_ports(self):
        out = variants.build_variants(CONF)
        self.assertEqual(3, len(out))
        self.assertIn("Endpoint = 194.180.34.9:443", out[0])
        self.assertIn("Endpoint = 194.180.34.9:1194", out[1])
        self.assertIn("Endpoint = 194.180.34.9:4500", out[2])

    def test_keys_and_address_survive(self):
        for body in variants.build_variants(CONF):
            self.assertIn("PrivateKey = AAAA", body)
            self.assertIn("PublicKey = BBBB", body)
            self.assertIn("Address = 10.2.0.2/32", body)

    def test_junk_values_differ_per_variant(self):
        out = variants.build_variants(CONF)
        self.assertIn("Jc = 3", out[0])
        self.assertIn("Jc = 5", out[1])
        self.assertIn("Jc = 8", out[2])

    def test_missing_endpoint_gives_no_variants(self):
        self.assertEqual([], variants.build_variants("[Interface]\nPrivateKey = A\n"))

    def test_count_is_capped_by_ports(self):
        out = variants.build_variants(CONF, count=5, ports=(443, 1194))
        self.assertEqual(2, len(out))


if __name__ == "__main__":
    unittest.main()
