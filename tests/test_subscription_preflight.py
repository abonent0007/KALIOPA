"""Предварительная проба подписки не должна блокировать обновление при сбое."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_subscriptions as subscriptions  # noqa: E402


class _Node:
    def __init__(self, identity):
        self.identity = identity


class _StubProbe:
    def __init__(self, enabled=True, result=None, error=None):
        self._enabled = enabled
        self._result = result or ([], [])
        self._error = error

    def enabled(self):
        return self._enabled

    def probe_nodes(self, nodes):
        if self._error is not None:
            raise self._error
        return self._result


class ProbedAddTests(unittest.TestCase):
    def setUp(self):
        self.by_identity = {"a": _Node("a"), "b": _Node("b"), "c": _Node("c")}
        self.messages = []

    def _run(self, stub, identities=("a", "b", "c")):
        with mock.patch.object(subscriptions, "nova_vless_preflight", stub):
            return subscriptions._probed_add_identities(
                list(identities), self.by_identity, self.messages.append, "test")

    def test_probe_failure_keeps_every_node(self):
        stub = _StubProbe(error=RuntimeError("no threads"))
        self.assertEqual(["a", "b", "c"], self._run(stub))
        self.assertTrue(self.messages and "беру все" in self.messages[0])

    def test_dead_node_is_removed_from_the_add_list(self):
        stub = _StubProbe(result=([_Node("a"), _Node("c")], [(_Node("b"), "timeout")]))
        self.assertEqual(["a", "c"], self._run(stub))
        self.assertTrue(any("отсеяно 1 из 3" in message for message in self.messages))

    def test_disabled_probe_keeps_every_node(self):
        self.assertEqual(["a", "b", "c"], self._run(_StubProbe(enabled=False)))

    def test_identities_without_nodes_are_left_alone(self):
        self.assertEqual(["a", "missing"], self._run(_StubProbe(), ("a", "missing")))


if __name__ == "__main__":
    unittest.main()
