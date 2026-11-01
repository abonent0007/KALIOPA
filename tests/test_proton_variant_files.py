"""Дополнительные файлы одного Proton-узла: порты, имена, выключатель."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_proton  # noqa: E402

CONF = """[Interface]
PrivateKey = AAAA
Address = 10.2.0.2/32
Jc = 5
Jmin = 59
Jmax = 103

[Peer]
PublicKey = BBBB
AllowedIPs = 0.0.0.0/0
Endpoint = 194.180.34.9:{port}
"""


class VariantFileTests(unittest.TestCase):
    def test_two_extra_ports_beside_the_base_one(self):
        files = nova_proton.variant_files("NL-FREE-1.conf", CONF.format(port=443), 443)
        self.assertEqual(["NL-FREE-1-p2.conf", "NL-FREE-1-p3.conf"], [name for name, _ in files])
        self.assertIn("Endpoint = 194.180.34.9:1194", files[0][1])
        self.assertIn("Endpoint = 194.180.34.9:4500", files[1][1])

    def test_base_port_outside_the_shortlist_keeps_two_variants(self):
        files = nova_proton.variant_files("NL-FREE-1.conf", CONF.format(port=88), 88)
        self.assertEqual(2, len(files))
        self.assertIn("Endpoint = 194.180.34.9:443", files[0][1])

    def test_env_switch_disables_variants(self):
        with mock.patch.dict(os.environ, {"NOVA_PROTON_VARIANTS": "0"}):
            self.assertEqual(
                [], nova_proton.variant_files("NL-FREE-1.conf", CONF.format(port=443), 443)
            )

    def test_variant_names_look_generated(self):
        self.assertTrue(nova_proton.is_generated_name("NL-FREE-1-p2.conf"))
        self.assertTrue(nova_proton.is_generated_name("NL-FREE-1"))
        self.assertFalse(nova_proton.is_generated_name("hand-dropped.conf"))

    def test_missing_endpoint_gives_no_variants(self):
        self.assertEqual([], nova_proton.variant_files("NL-FREE-1.conf", "[Interface]\n", 443))


if __name__ == "__main__":
    unittest.main()
