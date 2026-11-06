"""Один WARP-профиль в Custom AWG: локальная генерация, без чужих ключей.

Проверяем, что кнопка «Сгенерировать» не трогает WARPgen-набор, пишет
DNS/MTU/keepalive/I1 и создаёт следующий свободный `WARPgen_custom_NN`.
"""

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_warp_generator as gen  # noqa: E402

IDENTITY = {
    "private_key": "priv",
    "public_key": "pub",
    "peer_public_key": "peer",
    "ipv4": "172.16.0.2",
    "ipv6": "2606:4700:110::2",
}


class BuildConfTests(unittest.TestCase):
    def test_custom_dns_mtu_keepalive(self):
        text = gen.build_warp_conf(
            IDENTITY, "162.159.192.1", 2408, (3, 30, 60), "I1",
            dns="8.8.8.8", mtu=1400, keepalive=25,
        )
        self.assertIn("DNS = 8.8.8.8", text)
        self.assertIn("MTU = 1400", text)
        self.assertIn("PersistentKeepalive = 25", text)
        self.assertIn("I1 = I1", text)

    def test_defaults_are_unchanged(self):
        text = gen.build_warp_conf(IDENTITY, "162.159.192.1", 2408, (3, 30, 60))
        self.assertIn("DNS = 1.1.1.1, 1.0.0.1", text)
        self.assertIn("MTU = 1280", text)
        self.assertNotIn("PersistentKeepalive", text)


class GenerateCustomTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="kaliopa-custom-warp-")

    def run_generate(self, **kwargs):
        with mock.patch.object(gen, "_load_identity", return_value=(IDENTITY, "")), \
             mock.patch.object(gen, "_collect_verified",
                               return_value=([{"host": "162.159.192.1", "port": 2408,
                                               "rtt_ms": 42}], None)), \
             mock.patch.object(gen.nova_quic_initial, "pick_sni", return_value="www.example.com"), \
             mock.patch.object(gen.nova_quic_initial, "build_i1", return_value="I1-TEST"):
            return gen.generate_custom_one(self.base, "nova-go.exe", log=lambda _m: None, **kwargs)

    def test_creates_one_profile_with_optimal_defaults(self):
        result = self.run_generate()
        self.assertTrue(result["ok"], result)
        self.assertEqual("Custom/WARPgen_custom_01", result["profile_id"])
        path = pathlib.Path(self.base) / "profiles" / "Custom" / "WARPgen_custom_01.conf"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("MTU = 1280", text)
        self.assertIn("PersistentKeepalive = 25", text)
        self.assertIn("I1 = I1-TEST", text)
        self.assertIn("Endpoint = 162.159.192.1:2408", text)

    def test_second_generation_gets_the_next_name(self):
        self.run_generate()
        result = self.run_generate()
        self.assertEqual("Custom/WARPgen_custom_02", result["profile_id"])

    def test_manual_endpoint_skips_the_scan(self):
        with mock.patch.object(gen, "_collect_verified", side_effect=AssertionError("scan")):
            result = self.run_generate(host="188.114.96.1", port=500, dns="1.1.1.1",
                                       mtu=1400, keepalive=0, sni="", junk=(4, 40, 80))
        self.assertTrue(result["ok"], result)
        text = (pathlib.Path(self.base) / "profiles" / "Custom" / "WARPgen_custom_01.conf"
                ).read_text(encoding="utf-8")
        self.assertIn("Endpoint = 188.114.96.1:500", text)
        self.assertIn("MTU = 1400", text)
        self.assertNotIn("PersistentKeepalive", text)

    def test_it_does_not_touch_an_existing_warpgen_batch(self):
        batch = pathlib.Path(self.base) / "profiles" / "AWG Cloudflare"
        batch.mkdir(parents=True)
        (batch / "WARPgen_01.conf").write_text("keep", encoding="utf-8")
        self.run_generate()
        self.assertEqual("keep", (batch / "WARPgen_01.conf").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
