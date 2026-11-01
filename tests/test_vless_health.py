"""VLESS: мёртвые публичные узлы не должны перебираться каждый раз.

В замере 2026-10-31 из 246 профилей исходы были у 19 — и все провальные, а выбранный
узел имел серию из 15 отказов. Сортировка ставила такие в конец, но группа всё равно
шла по ним, тратя по 12 с на каждый. Узел с серией `VLESS_DEAD_STREAK` и без успеха
после последнего отказа выпадает из автоматического перебора на сутки.
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_profiles as profiles  # noqa: E402


def record(name="dead"):
    return {"id": f"VLESS/{name}", "name": name, "group": "VLESS"}


def stats_for(entry):
    return {f"VLESS/dead": entry}


class VlessQuarantineTests(unittest.TestCase):
    def test_streak_at_limit_is_quarantined(self):
        now = time.time()
        entry = {"fail_streak": profiles.VLESS_DEAD_STREAK, "last_fail_at": now - 60}
        self.assertTrue(profiles.vless_quarantined(record(), stats_for(entry), now=now))

    def test_streak_below_limit_is_not_quarantined(self):
        now = time.time()
        entry = {"fail_streak": profiles.VLESS_DEAD_STREAK - 1, "last_fail_at": now - 60}
        self.assertFalse(profiles.vless_quarantined(record(), stats_for(entry), now=now))

    def test_success_after_failure_lifts_quarantine(self):
        now = time.time()
        entry = {"fail_streak": 9, "last_fail_at": now - 600, "last_ok_at": now - 300}
        self.assertFalse(profiles.vless_quarantined(record(), stats_for(entry), now=now))

    def test_old_failure_expires(self):
        now = time.time()
        entry = {
            "fail_streak": 9,
            "last_fail_at": now - profiles.VLESS_MEMORY_SEC - 60,
        }
        self.assertFalse(profiles.vless_quarantined(record(), stats_for(entry), now=now))

    def test_missing_entry_is_not_quarantined(self):
        self.assertFalse(profiles.vless_quarantined(record(), {}, now=time.time()))


if __name__ == "__main__":
    unittest.main()
