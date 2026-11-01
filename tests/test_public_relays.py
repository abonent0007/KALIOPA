"""Снимок публичных релеев: чужие объекты не должны ломать отрисовку.

`build_public_relay_snapshot` опрашивает менеджеры Telegram/WhatsApp. Раньше три
одинаковых try/except были размазаны по телу, и любой новый атрибут легко было
забыть обернуть. Тест фиксирует контракт: исключение в `is_ready`, `port` или
`server.running` даёт fallback на данные спецификации, а не падение.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_public_relays as relays  # noqa: E402


class _ReadyManager:
    port = 21372

    def is_ready(self):
        return True


class _BrokenManager:
    @property
    def port(self):
        raise RuntimeError("port is not available yet")

    def is_ready(self):
        raise RuntimeError("manager is half-initialized")


class _ZeroPortManager:
    port = 0

    def is_ready(self):
        return False


class PublicRelaySpecTests(unittest.TestCase):
    def test_telegram_is_enabled_by_default(self):
        specs = relays.get_public_relay_specs("current")
        self.assertTrue(specs["telegram"].enabled)
        self.assertFalse(specs["telegram"].planned_only)

    def test_whatsapp_stays_planned(self):
        specs = relays.get_public_relay_specs("auto")
        self.assertFalse(specs["whatsapp"].enabled)
        self.assertTrue(specs["whatsapp"].planned_only)

    def test_env_switch_disables_telegram(self):
        with mock.patch.dict(os.environ, {"NOVA_TELEGRAM_RELAY": "0"}):
            specs = relays.get_public_relay_specs("current")
        self.assertFalse(specs["telegram"].enabled)


class PublicRelaySnapshotTests(unittest.TestCase):
    def test_ready_manager_uses_its_port(self):
        snapshot = relays.build_public_relay_snapshot("current", {"telegram": _ReadyManager()})
        self.assertTrue(snapshot["telegram"]["ready"])
        self.assertTrue(snapshot["telegram"]["running"])
        self.assertEqual("127.0.0.1:21372", snapshot["telegram"]["bind"])

    def test_broken_manager_falls_back_to_spec(self):
        snapshot = relays.build_public_relay_snapshot("current", {"telegram": _BrokenManager()})
        self.assertFalse(snapshot["telegram"]["ready"])
        self.assertFalse(snapshot["telegram"]["running"])
        self.assertEqual("127.0.0.1:1372", snapshot["telegram"]["bind"])

    def test_zero_port_falls_back_to_spec(self):
        snapshot = relays.build_public_relay_snapshot("current", {"telegram": _ZeroPortManager()})
        self.assertEqual("127.0.0.1:1372", snapshot["telegram"]["bind"])

    def test_missing_managers_are_reported_not_raised(self):
        snapshot = relays.build_public_relay_snapshot("current", None)
        self.assertEqual({"telegram", "whatsapp"}, set(snapshot))
        self.assertFalse(snapshot["telegram"]["ready"])


if __name__ == "__main__":
    unittest.main()
