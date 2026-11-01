"""Предварительная проба VLESS: параллельность, причины отказа, выключатель."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_vless_preflight as preflight  # noqa: E402


class _Node:
    def __init__(self, identity, host="example.org", port=443, sni=""):
        self.identity = identity
        self.host = host
        self.port = port
        self.sni = sni


class ProbeTests(unittest.TestCase):
    def test_probe_nodes_splits_alive_and_rejected(self):
        nodes = [_Node("a"), _Node("b"), _Node("c")]

        def prober(node, timeout):
            return "" if node.identity != "b" else "нет TCP: timeout"

        alive, rejected = preflight.probe_nodes(nodes, prober=prober)
        self.assertEqual({"a", "c"}, {node.identity for node in alive})
        self.assertEqual([("b", "нет TCP: timeout")], [(node.identity, reason) for node, reason in rejected])

    def test_prober_exception_is_a_rejection_not_a_crash(self):
        def prober(node, timeout):
            raise RuntimeError("boom")

        alive, rejected = preflight.probe_nodes([_Node("a")], prober=prober)
        self.assertEqual([], alive)
        self.assertEqual("RuntimeError", rejected[0][1])

    def test_missing_target_is_rejected_without_network(self):
        self.assertTrue(preflight.probe_node(_Node("a", host="", port=0)))

    def test_switch_disables_the_probe(self):
        with mock.patch.dict(os.environ, {"NOVA_VLESS_PREFLIGHT": "0"}):
            self.assertFalse(preflight.enabled())
        with mock.patch.dict(os.environ, {"NOVA_VLESS_PREFLIGHT": "1"}):
            self.assertTrue(preflight.enabled())

    def test_tls_probe_is_opt_in(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(preflight.tls_enabled())
        with mock.patch.dict(os.environ, {"NOVA_VLESS_PREFLIGHT_TLS": "1"}):
            self.assertTrue(preflight.tls_enabled())


if __name__ == "__main__":
    unittest.main()
