"""Настройки генератора Custom WARP: пресеты, границы, сохранение.

Проверяем, что мусор в файле и в полях не ломает генератор: неизвестные ключи
отбрасываются, числа зажимаются, «рваный» джанк становится случайным, а
некорректный ручной endpoint откатывается к авто.
"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_warp_custom_settings as settings  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_empty_input_is_the_defaults(self):
        data = settings.normalize(None)
        self.assertEqual(settings.DEFAULTS, data)
        self.assertEqual("optimal", data["preset"])

    def test_numbers_are_clamped(self):
        data = settings.normalize({"mtu": 9999, "keepalive": -5, "endpoint_port": 0})
        self.assertEqual(settings.MTU_MAX, data["mtu"])
        self.assertEqual(0, data["keepalive"])
        self.assertEqual(1, data["endpoint_port"])

    def test_bad_values_fall_back(self):
        data = settings.normalize({
            "preset": "turbo", "endpoint_mode": "sometimes", "endpoint_host": "не хост",
            "dns": ";;;", "sni": "bad sni!", "mtu": "abc",
        })
        self.assertEqual("optimal", data["preset"])
        self.assertEqual("auto", data["endpoint_mode"])
        self.assertEqual("", data["endpoint_host"])
        self.assertEqual(settings.DNS_DEFAULT, data["dns"])
        self.assertEqual("", data["sni"])
        self.assertEqual(1280, data["mtu"])

    def test_a_partial_junk_is_treated_as_random(self):
        data = settings.normalize({"jc": 4, "jmin": 40, "jmax": 0})
        self.assertEqual((0, 0, 0), (data["jc"], data["jmin"], data["jmax"]))

    def test_a_complete_junk_is_kept(self):
        data = settings.normalize({"jc": 4, "jmin": 40, "jmax": 70})
        self.assertEqual((4, 40, 70), (data["jc"], data["jmin"], data["jmax"]))

    def test_reversed_junk_bounds_become_random(self):
        data = settings.normalize({"jc": 4, "jmin": 80, "jmax": 40})
        self.assertEqual(0, data["jc"])


class PresetTests(unittest.TestCase):
    def test_fast_preset_pins_a_proven_sni_and_more_endpoints(self):
        data = settings.apply_preset("fast")
        self.assertEqual("fast", data["preset"])
        self.assertEqual(settings.SNI_DEFAULT, data["sni"])
        self.assertEqual(3, data["endpoint_attempts"])
        self.assertEqual((3, 30, 55), (data["jc"], data["jmin"], data["jmax"]))

    def test_compat_preset_uses_a_smaller_mtu(self):
        self.assertEqual(1240, settings.apply_preset("compat")["mtu"])

    def test_custom_keeps_the_current_values(self):
        current = settings.normalize({"preset": "fast", "mtu": 1300})
        data = settings.apply_preset("custom", current)
        self.assertEqual(1300, data["mtu"])
        self.assertEqual("custom", data["preset"])


class ResolveTests(unittest.TestCase):
    def test_auto_endpoint_does_not_pass_a_manual_one(self):
        options = settings.resolve({"endpoint_mode": "auto", "endpoint_host": "1.2.3.4"})
        self.assertEqual("", options["host"])
        self.assertEqual(0, options["port"])

    def test_manual_endpoint_and_junk_are_passed(self):
        options = settings.resolve({
            "endpoint_mode": "manual", "endpoint_host": "188.114.96.1", "endpoint_port": 500,
            "jc": 4, "jmin": 40, "jmax": 70, "dns": "8.8.8.8", "mtu": 1340, "keepalive": 0,
            "sni": "www.ozon.ru",
        })
        self.assertEqual(("188.114.96.1", 500), (options["host"], options["port"]))
        self.assertEqual((4, 40, 70), options["junk"])
        self.assertEqual("8.8.8.8", options["dns"])
        self.assertEqual(1340, options["mtu"])
        self.assertEqual(0, options["keepalive"])
        self.assertEqual("www.ozon.ru", options["sni"])

    def test_random_junk_is_none(self):
        self.assertIsNone(settings.resolve({})["junk"])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="kaliopa-warp-settings-")

    def test_roundtrip(self):
        saved = settings.save(self.base, {"preset": "fast", "mtu": 1300})
        self.assertEqual("fast", saved["preset"])
        path = pathlib.Path(self.base) / "temp" / settings.FILENAME
        self.assertTrue(path.is_file())
        loaded = settings.load(self.base)
        self.assertEqual(1300, loaded["mtu"])
        self.assertNotIn("PrivateKey", path.read_text(encoding="utf-8"))

    def test_a_broken_file_is_not_an_error(self):
        path = pathlib.Path(self.base) / "temp" / settings.FILENAME
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(settings.DEFAULTS, settings.load(self.base))

    def test_missing_file_returns_defaults(self):
        self.assertEqual(settings.DEFAULTS, settings.load(self.base))


if __name__ == "__main__":
    unittest.main()
