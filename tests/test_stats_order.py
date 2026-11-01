"""Порядок узлов: сначала без отказов, затем по свежему RTT, затем по имени.

Запрос владельца — стабильное соединение. Раньше `_stats_order` сортировал только по числу
отказов и имени, поэтому первый по алфавиту медленный узел выбирался раньше быстрого.
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_profiles as profiles  # noqa: E402


def rec(name):
    return {"id": f"MASQUE/{name}", "name": name}


def stats(**kwargs):
    return {f"MASQUE/{name}": entry for name, entry in kwargs.items()}


class StatsOrderTests(unittest.TestCase):
    def test_fastest_goes_first(self):
        now = time.time()
        data = stats(
            slow={"fail_streak": 0, "rtt_ms": 420, "rtt_at": now - 60},
            fast={"fail_streak": 0, "rtt_ms": 40, "rtt_at": now - 60},
            never={},
        )
        ordered = profiles._stats_order([rec("slow"), rec("fast"), rec("never")], data, now=now)
        self.assertEqual(["fast", "slow", "never"], [r["name"] for r in ordered])

    def test_failures_outrank_speed(self):
        now = time.time()
        data = stats(
            fast_but_dead={"fail": 2, "rtt_ms": 20, "rtt_at": now - 60,
                           "last_fail_at": now - 30},
            slower_alive={"fail_streak": 0, "rtt_ms": 300, "rtt_at": now - 60},
        )
        ordered = profiles._stats_order([rec("fast_but_dead"), rec("slower_alive")], data, now=now)
        self.assertEqual("slower_alive", ordered[0]["name"])

    def test_stale_rtt_is_ignored(self):
        now = time.time()
        data = stats(old_fast={"fail_streak": 0, "rtt_ms": 10,
                               "rtt_at": now - profiles.VLESS_MEMORY_SEC - 60})
        ordered = profiles._stats_order([rec("old_fast")], data, now=now)
        self.assertEqual(1, len(ordered))


if __name__ == "__main__":
    unittest.main()
