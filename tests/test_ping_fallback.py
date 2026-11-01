"""Проба узла: ICMP первым, TCP — фолбэк, общий бюджет времени ограничен."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_ping  # noqa: E402


class ProbeFallbackTests(unittest.TestCase):
    def test_icmp_answer_skips_tcp(self):
        calls = []
        result = nova_ping.probe_host(
            "192.0.2.1",
            icmp=lambda host, timeout: 12,
            tcp=lambda host, port, timeout: calls.append(port) or 34,
        )
        self.assertEqual((12, "icmp"), (result.ms, result.method))
        self.assertEqual([], calls)

    def test_blocked_icmp_falls_through_to_the_first_open_tcp_port(self):
        calls = []

        def tcp(host, port, timeout):
            calls.append(port)
            return 41 if port == 443 else None

        result = nova_ping.probe_host(
            "192.0.2.1", tcp_ports=(80, 443), icmp=lambda host, timeout: None, tcp=tcp
        )
        self.assertEqual((41, "tcp"), (result.ms, result.method))
        self.assertEqual([80, 443], calls)

    def test_silent_host_reports_no_latency(self):
        result = nova_ping.probe_host(
            "192.0.2.1", icmp=lambda host, timeout: None, tcp=lambda host, port, timeout: None
        )
        self.assertIsNone(result.ms)
        self.assertEqual("", result.method)


if __name__ == "__main__":
    unittest.main()
