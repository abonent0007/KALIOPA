"""US/AM тоже получает WARP-транспорт, а не только EU.

Живой случай 2026-11-08: Direct US отдаёт discover 801/таймаут, AM-края по TCP
отвечают, но туннель молчит; тот же `-country AM` через WARP-слот отдаёт 200.
Старая машина состояний предлагала WARP только для EU, поэтому выбранный US
перезапускался напрямую бесконечно, 1371 не поднимался, а ИИ уходил на WARP с
RU-выходом.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_opera_failover as failover  # noqa: E402

WARP = "socks5h://127.0.0.1:1370"


def exhaust_direct(controller, warp_usable=False, warp_proxy=""):
    decision = None
    for _ in range(controller.direct_failure_limit):
        decision = controller.next_after_failure(1000.0, warp_usable=warp_usable,
                                                warp_proxy=warp_proxy)
    return decision


class AmOverWarpTests(unittest.TestCase):
    def test_us_falls_back_to_warp(self):
        controller = failover.OperaFailoverController(desired_country="US")
        decision = exhaust_direct(controller, warp_usable=True, warp_proxy=WARP)
        self.assertEqual("warp", decision.transport)
        self.assertEqual(WARP, decision.full_proxy)
        self.assertEqual("desired-am-over-warp", decision.reason)
        self.assertEqual("AM", decision.country)

    def test_us_without_warp_retries_in_place(self):
        controller = failover.OperaFailoverController(desired_country="US")
        decision = exhaust_direct(controller, warp_usable=False)
        self.assertEqual("direct", decision.transport)
        self.assertEqual("desired-am-retry", decision.reason)
        self.assertEqual("AM", decision.country)

    def test_eu_keeps_its_own_reason(self):
        controller = failover.OperaFailoverController(desired_country="EU")
        decision = exhaust_direct(controller, warp_usable=True, warp_proxy=WARP)
        self.assertEqual("desired-eu-over-warp", decision.reason)
        self.assertEqual("warp", decision.transport)

    def test_a_working_us_after_warp_resets_the_counters(self):
        controller = failover.OperaFailoverController(desired_country="US")
        exhaust_direct(controller, warp_usable=True, warp_proxy=WARP)
        controller.transport = "warp"
        controller.warp_failures = 0
        controller.record_success(2000.0)
        self.assertEqual(0, controller.direct_failures)
        self.assertEqual(0, controller.retry_round)


if __name__ == "__main__":
    unittest.main()
