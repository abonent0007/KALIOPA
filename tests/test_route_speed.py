"""Скорость маршрута и агрегация трафик-логов.

Релей раньше писал строку `traffic …` на каждое соединение каждые 8 секунд и
выбирал маршрут по фиксированному порядку имён. Тест фиксирует два контракта:
лог агрегируется по маршруту не чаще `TRAFFIC_LOG_INTERVAL`, а измеренная
скорость сортирует прокси-кандидатов, никогда не поднимая `direct`.
"""

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tgrelay import transparent_relay as relay  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        relay._route_speed.clear()
        relay._route_speed_loaded = True  # не трогаем temp/tgrelay_routes.json
        relay._route_speed_saved_at = time.time()
        relay._traffic_agg.clear()

    def tearDown(self):
        relay._route_speed.clear()
        relay._traffic_agg.clear()


class RouteSpeedOrderTests(_Base):
    def test_faster_proxy_goes_first_and_direct_stays_last(self):
        relay._route_speed["opera-http"] = {"rate_down": 9000.0, "updated": time.time()}
        relay._route_speed["warp-socks"] = {"rate_down": 100.0, "updated": time.time()}
        attempts = [
            {"kind": "socks5", "label": "warp-socks"},
            {"kind": "http", "label": "opera-http"},
            {"kind": "direct", "label": "direct"},
        ]
        ordered = relay._order_attempts_by_speed(attempts)
        self.assertEqual([a["label"] for a in ordered], ["opera-http", "warp-socks", "direct"])

    def test_unknown_routes_keep_their_order(self):
        attempts = [
            {"kind": "socks5", "label": "warp-socks"},
            {"kind": "http", "label": "opera-http"},
        ]
        ordered = relay._order_attempts_by_speed(attempts)
        self.assertEqual([a["label"] for a in ordered], ["warp-socks", "opera-http"])

    def test_native_health_bucket_beats_speed(self):
        relay._route_speed["warp-socks"] = {"rate_down": 999999.0, "updated": time.time()}
        states = {"warp-socks": False, "opera-http": True}
        attempts = [
            {"kind": "socks5", "label": "warp-socks"},
            {"kind": "http", "label": "opera-http"},
        ]
        with mock.patch.object(relay, "_native_state", side_effect=lambda dc, label: states.get(label)):
            ordered = relay._order_native_attempts(attempts, 2)
        self.assertEqual([a["label"] for a in ordered], ["opera-http", "warp-socks"])

    def test_expired_sample_scores_zero(self):
        relay._route_speed["opera-http"] = {"rate_down": 9000.0, "updated": time.time() - relay.ROUTE_SPEED_TTL - 5}
        self.assertEqual(relay._route_speed_score("opera-http"), 0.0)


class TrafficAggregateTests(_Base):
    LABEL = "path=tcp-fallback route=warp-socks target=149.154.167.51:443 media=True"

    def test_label_is_reduced_to_route(self):
        key, route = relay._traffic_stats_key(self.LABEL)
        self.assertEqual(key, "path=tcp-fallback route=warp-socks")
        self.assertEqual(route, "warp-socks")

    def test_lines_are_throttled_per_route(self):
        lines = []
        key, route = relay._traffic_stats_key(self.LABEL)
        relay._note_traffic(key, route, 100, 200, lines.append, 1000.0)
        relay._note_traffic(key, route, 100, 200, lines.append, 1010.0)
        self.assertEqual(len(lines), 1, "второй тик раньше интервала не пишет строку")
        relay._note_traffic(key, route, 50, 50, lines.append, 1061.0)
        self.assertEqual(len(lines), 2)
        self.assertIn("route=warp-socks", lines[0])
        self.assertIn("sessions=2", lines[1])

    def test_measured_rate_feeds_route_speed(self):
        lines = []
        key, route = relay._traffic_stats_key(self.LABEL)
        relay._note_traffic(key, route, 10, 4000, lines.append, 1000.0)
        self.assertGreater(relay._route_speed_score("warp-socks"), 0.0)

    def test_different_targets_share_one_bucket(self):
        key_one, route = relay._traffic_stats_key(self.LABEL)
        key_two, _ = relay._traffic_stats_key(
            "path=tcp-fallback route=warp-socks target=149.154.167.41:443 media=False"
        )
        self.assertEqual(key_one, key_two)


if __name__ == "__main__":
    unittest.main()
