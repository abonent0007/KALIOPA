"""Кольцо дополнительного VPN: Proton — шаг «Авто», а не только именованный выбор.

Upstream 1.44 ввёл шаг `profile/AWG Proton` между Opera и Tor (D35). Тест фиксирует порядок,
поворот кольца к последнему рабочему шагу и то, что именованный выбор по-прежнему один.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_vpn_slots as slots  # noqa: E402

PROTON = ("profile", slots._GROUP_PROTON)


class SecondaryRingTests(unittest.TestCase):
    def test_auto_ring_starts_with_opera_then_proton_then_tor(self):
        ring = slots.secondary_attempts({"mode": "auto", "opera_region": "US"})
        self.assertEqual(
            [("opera", "US"), PROTON, ("tor", "auto")],
            ring,
        )

    def test_ring_rotates_to_last_good_kind(self):
        ring = slots.secondary_attempts({"mode": "auto"}, {"kind": "tor"})
        self.assertEqual([("tor", "auto"), ("opera", "EU"), PROTON], ring)

        ring = slots.secondary_attempts({"mode": "auto"}, {"kind": "profile"})
        self.assertEqual([PROTON, ("tor", "auto"), ("opera", "EU")], ring)

    def test_named_choices_stay_single(self):
        self.assertEqual([("opera", "EU")], slots.secondary_attempts({"mode": "opera"}))
        self.assertEqual([("tor", "auto")], slots.secondary_attempts({"mode": "tor"}))
        self.assertEqual(
            [("profile", "VLESS")],
            slots.secondary_attempts({"mode": "profile", "profile_group": "VLESS"}),
        )

    def test_preferred_countries_match_the_measured_order(self):
        self.assertEqual(
            ("NL", "NO", "PL", "RO", "CA", "MX", "US", "SG", "JP", "CH"),
            slots._PREFERRED_COUNTRIES,
        )


if __name__ == "__main__":
    unittest.main()
