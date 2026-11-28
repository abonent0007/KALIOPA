"""Конструктор AWG 1.5/2.0/3.0/3.1 (порт awgconfig.com, AGPL-3.0)."""

import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_awg3 as awg  # noqa: E402

IDENTITY = {
    "private_key": "a" * 44 + "=",
    "public_key": "b" * 44 + "=",
    "peer_public_key": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
    "ipv4": "172.16.0.2",
    "ipv6": "2606:4700:110:8ac2:b546:861b:fa33:5ff2",
}


class ProfileTests(unittest.TestCase):
    def test_aliases_normalize(self):
        self.assertEqual("legacy", awg.normalize_mode("1.5"))
        self.assertEqual("awg2", awg.normalize_mode("v2"))
        self.assertEqual("awg3", awg.normalize_mode("3.0"))
        self.assertEqual("awg31", awg.normalize_mode("awg3.1"))
        self.assertEqual("legacy", awg.normalize_mode("мусор"))

    def test_warp_safe_fixes_wire_format(self):
        safe = awg.enforce_warp_safe({"mode": "awg3", "S1": 9, "H1": "7"})
        self.assertEqual(0, safe["S1"])
        self.assertEqual("1", safe["H1"])

    def test_disable_cookies_only_for_31(self):
        with self.assertRaises(ValueError):
            awg.enforce_warp_safe({"mode": "awg3", "DisableCookies": "on"})
        safe = awg.enforce_warp_safe({"mode": "awg31", "DisableCookies": "on"})
        self.assertEqual("on", safe["DisableCookies"])

    def test_random_trailers_are_rejected(self):
        with self.assertRaises(ValueError):
            awg.enforce_warp_safe({"RandomTrailers": "on"})


class ConfigBuilderTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(1)

    def test_awg3_interface_has_timings_and_padding(self):
        timings = {key: awg.random_timing(self.rng, key) for key in awg.TIMING_DEFAULTS}
        timings["ContentPaddingAddition"] = "50"
        text = awg.build_interface(identity=IDENTITY, mode="awg3",
                                   client_ipv4=IDENTITY["ipv4"],
                                   client_ipv6=IDENTITY["ipv6"],
                                   i1="<b 0xdead>", extra_cps=awg.generate_i2_i5(self.rng),
                                   timings=timings)
        for field in awg.TIMING_DEFAULTS:
            self.assertIn(f"{field} = ", text)
        self.assertIn("ContentPaddingAddition = 50", text)
        self.assertIn("I1 = <b 0xdead>", text)
        self.assertIn("I2 = ", text)
        self.assertNotIn("MTU = 1280\n\n", text)

    def test_awg31_writes_disable_cookies(self):
        text = awg.build_interface(identity=IDENTITY, mode="awg31",
                                   client_ipv4=IDENTITY["ipv4"],
                                   disable_cookies="on")
        self.assertIn("DisableCookies = on", text)

    def test_legacy_interface_has_no_timings(self):
        text = awg.build_interface(identity=IDENTITY, mode="legacy",
                                   client_ipv4=IDENTITY["ipv4"], i1="")
        self.assertNotIn("RekeyAfterTime", text)
        self.assertNotIn("I1 = ", text)
        self.assertIn("Jc = 4", text)

    def test_config_has_peer_section(self):
        text = awg.build_config(IDENTITY, "162.159.192.1", 2408, mode="awg3",
                                client_ipv4=IDENTITY["ipv4"])
        self.assertIn("[Peer]", text)
        self.assertIn(f"PublicKey = {IDENTITY['peer_public_key']}", text)
        self.assertIn("AllowedIPs = 0.0.0.0/0, ::/0", text)
        self.assertIn("Endpoint = 162.159.192.1:2408", text)


class CpsTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(7)

    def test_static_payload_is_fixed_bytes(self):
        value = awg.cps_payload(self.rng)
        self.assertTrue(value.startswith("<b 0x"))
        self.assertGreater(len(value), 1000)

    def test_sip_pair_shapes(self):
        i1, i2 = awg.sip_pair(self.rng)
        self.assertTrue(i1.startswith("<b 0x"))
        self.assertTrue(i2.startswith("<b 0x"))
        self.assertNotEqual(i1, i2)

    def test_structured_payloads(self):
        self.assertTrue(awg.stun_payload(self.rng).startswith("<b 0x"))
        self.assertTrue(awg.dtls_payload(self.rng).startswith("<b 0x"))
        self.assertTrue(awg.dns_template(self.rng).startswith("<r 2><b 0x"))

    def test_i2_i5_runtime_chains(self):
        chains = awg.generate_i2_i5(self.rng)
        self.assertEqual({"I2", "I3", "I4", "I5"}, set(chains))
        for value in chains.values():
            self.assertTrue(value.startswith("<"))
            self.assertIn(">", value)

    def test_endpoint_prefixes_do_not_overlap_ordinary_cf_net(self):
        self.assertNotIn("188.114.96.0/22", awg.WARP_ENDPOINT_PREFIXES_V4)


class OptionsTests(unittest.TestCase):
    def test_defaults(self):
        opts = awg.normalize_options(None)
        self.assertEqual("awg3", opts["mode"])
        self.assertEqual(1, opts["count"])
        self.assertEqual("auto", opts["endpoint_mode"])

    def test_clamps_and_validation(self):
        opts = awg.normalize_options({"count": 999, "port": 0, "dns": ";;;",
                                      "cps_protocol": "мусор", "mode": "v3.1",
                                      "disable_cookies": True})
        self.assertEqual(20, opts["count"])
        self.assertEqual(1, opts["port"])
        self.assertEqual(awg.DEFAULT_OPTIONS["dns"], opts["dns"])
        self.assertEqual("auto", opts["cps_protocol"])
        self.assertEqual("awg31", opts["mode"])
        self.assertTrue(opts["disable_cookies"])

    def test_build_many_honours_count(self):
        endpoints = [("162.159.192.1", 2408), ("162.159.192.2", 2408)]
        texts = awg.build_many(IDENTITY, endpoints, {"count": 2, "extra_cps": False})
        self.assertEqual(2, len(texts))
        self.assertTrue(all("[Peer]" in text for text in texts))


if __name__ == "__main__":
    unittest.main()
