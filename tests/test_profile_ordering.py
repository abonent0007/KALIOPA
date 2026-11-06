"""Порядок AWG Cloudflare: рабочие узлы раньше «красивого» пинга.

`warp-generated-state.json` хранит 999 мс, пока скан не измерил хост. Если
верить только ему, все свои профили равны и группа идёт по имени:
WARPgen_01 первым, хотя 09 пингует 28 мс. Но 09 при этом отказывает в
туннеле, поэтому низкий ping не должен обгонять профиль, который уже вёз
трафик.
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_profiles  # noqa: E402
import nova_profiles_ui as ui  # noqa: E402


def rec(name, origin="generated"):
    return {
        "id": "AWG Cloudflare/" + name,
        "group": "AWG Cloudflare",
        "name": name,
        "origin": origin,
        "valid": True,
        "endpoint": "162.159.192.1:2408",
    }


def stats(ok=0, fail=0, rtt=999, last_ok=0, last_fail=0, fail_streak=0):
    now = time.time()
    return {"ok": ok, "fail": fail, "rtt_ms": rtt, "rtt_at": now - 10,
            "last_ok_at": now - 20 if last_ok else 0,
            "last_fail_at": now - 20 if last_fail else 0,
            "fail_streak": fail_streak, "last_ms": 2000}


class CloudflareOrderTests(unittest.TestCase):
    def setUp(self):
        self.records = [rec("WARPgen_01"), rec("WARPgen_02"), rec("WARPgen_03"),
                        rec("WARPgen_04"), rec("WARPgen_09"), rec("WARPgen_15")]
        self.state = {"profiles": {name: {"failures": 0, "rtt_ms": 999}
                                   for name in ("WARPgen_01", "WARPgen_02", "WARPgen_03",
                                                "WARPgen_04", "WARPgen_09", "WARPgen_15")}}
        self.stats = {
            "AWG Cloudflare/WARPgen_01": stats(ok=7, rtt=92, last_ok=5_000),
            "AWG Cloudflare/WARPgen_02": stats(ok=3, rtt=99, last_ok=4_000),
            "AWG Cloudflare/WARPgen_03": stats(ok=0, rtt=78),
            "AWG Cloudflare/WARPgen_04": stats(ok=0, rtt=32, last_fail=4_000, fail_streak=1),
            "AWG Cloudflare/WARPgen_09": stats(ok=0, rtt=28, last_fail=4_000, fail_streak=1),
            "AWG Cloudflare/WARPgen_15": stats(ok=1, rtt=92, last_ok=6_000),
        }

    def test_failed_low_ping_is_not_in_the_lead(self):
        lead, _pool, rest = nova_profiles._cloudflare_segments(
            self.records, "", self.state, self.stats)
        names = [r["name"] for r in lead]
        self.assertNotIn("WARPgen_09", names)
        self.assertNotIn("WARPgen_04", names)
        self.assertEqual("WARPgen_01", names[0])
        self.assertEqual("WARPgen_02", names[1])
        self.assertIn("WARPgen_09", [r["name"] for r in rest])

    def test_stats_rtt_overrides_the_999_placeholder(self):
        failures, known, rtt = nova_profiles._generated_metrics(
            self.state, self.records[1], self.stats)
        self.assertEqual(0, failures)
        self.assertEqual(1, known)
        self.assertEqual(99, rtt)

    def test_live_profile_is_first_and_failed_rows_are_last(self):
        rows = sorted(self.records, key=lambda r: ui._cloudflare_sort_key(
            r, self.stats, "AWG Cloudflare/WARPgen_15"))
        self.assertEqual("WARPgen_15", rows[0]["name"])
        self.assertEqual("WARPgen_01", rows[1]["name"])
        self.assertIn(rows[-1]["name"], ("WARPgen_04", "WARPgen_09"))


if __name__ == "__main__":
    unittest.main()
