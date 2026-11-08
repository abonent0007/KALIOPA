"""Политика KALIOPA: PAC 1370/1371/DIRECT, Telegram WARP, Tor/VLESS резерв."""

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "tools"))

import route_policy_check as policy  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_clean_config_matches(self):
        settings = {
            "secondary": {"mode": "opera"},
            "opera_region": "EU",
            "routes": {"browser": "auto", "telegram": "warp", "ai_apps": "opera"},
        }
        self.assertEqual([], policy.check_settings(settings))

    def test_tor_as_secondary_is_reported(self):
        settings = {
            "secondary": {"mode": "tor"},
            "opera_region": "EU",
            "routes": {"browser": "auto", "telegram": "auto", "ai_apps": "warp"},
        }
        issues = policy.check_settings(settings)
        self.assertTrue(any("secondary.mode" in issue for issue in issues))
        self.assertTrue(any("telegram" in issue for issue in issues))


class PacTests(unittest.TestCase):
    def test_pac_with_all_three_routes_is_ok(self):
        pac = 'return "SOCKS5 127.0.0.1:1370; PROXY 127.0.0.1:1371; DIRECT";'
        self.assertEqual([], policy.check_pac(pac))

    def test_pac_with_tor_port_is_rejected(self):
        pac = 'return "SOCKS5 127.0.0.1:1370; SOCKS5 127.0.0.1:1375";'
        issues = policy.check_pac(pac)
        self.assertTrue(any("1375" in issue for issue in issues))


class PortTests(unittest.TestCase):
    def test_required_open_and_reserve_closed(self):
        opened = {1369, 1370, 1371, 1372}
        closed = {1375, 1378, 1379, 1380}
        self.assertEqual([], policy.check_ports(opened, closed))

    def test_reserve_port_open_is_reported(self):
        issues = policy.check_ports({1369, 1370, 1371, 1372, 1375}, {1378, 1379, 1380})
        self.assertTrue(any("1375" in issue for issue in issues))


class PrimaryTests(unittest.TestCase):
    def test_one_backend_profile_is_ok(self):
        selection = {"mode": "profile", "group": "MASQUE", "profile": "MASQUE/Cloudflare MASQUE 2"}
        self.assertEqual([], policy.check_primary(selection))

    def test_unknown_primary_group_is_reported(self):
        issues = policy.check_primary({"mode": "group", "group": "Strange Group"})
        self.assertTrue(any("слотов" in issue for issue in issues))

    def test_profile_mode_without_id_is_reported(self):
        issues = policy.check_primary({"mode": "profile", "group": "MASQUE", "profile": ""})
        self.assertTrue(any("profile id" in issue for issue in issues))


class SourceGuardTests(unittest.TestCase):
    def test_hidden_tor_fallback_is_auto_only(self):
        text = (BASE / "nova.pyw").read_text(encoding="utf-8", errors="ignore")
        self.assertIn("secondary_mode == nova_vpn_slots.SECONDARY_AUTO", text)
        self.assertIn("secondary_kind = nova_vpn_slots.SECONDARY_TOR", text)


if __name__ == "__main__":
    unittest.main()
