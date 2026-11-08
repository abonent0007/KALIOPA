"""Схема Route Lab в программе: файл, порядок PAC, режимы, настройки."""

import copy
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "resources"))

import nova_route_spec as spec  # noqa: E402

SHIPPED = BASE / "resources" / "nova_route_spec.json"
TEMPLATE = BASE / "tools" / "route-editor" / "templates" / "kaliopa-clean.json"

CLEAN_SETTINGS = {
    "opera_region": "US",
    "secondary": {"mode": "opera"},
    "routes": {"browser": "auto", "telegram": "warp", "ai_apps": "opera"},
}


def hybrid_pac():
    return "\n".join((
        'var pac_mode = "hybrid";',
        "function FindProxyForURL(url, host) {",
        '    if (matchDomain(user_direct, host)) return "DIRECT";',
        '    if (matchDomain(user_ru, host)) return "SOCKS5 127.0.0.1:1370; PROXY 127.0.0.1:1371";',
        '    if (matchDomain(exclude, host)) return "DIRECT";',
        '    if (isLocalDirect(host)) return "DIRECT";',
        '    if (matchDomain(ai_apps, host)) return "PROXY 127.0.0.1:1371";',
        '    if (matchDomain(youtube, host)) return "PROXY 127.0.0.1:1371; SOCKS5 127.0.0.1:1370";',
        '    if (matchDomain(ru, host)) return "SOCKS5 127.0.0.1:1370; PROXY 127.0.0.1:1371";',
        '    return "DIRECT";',
        "}",
        "function FindProxyForURLEx(url, host) { return FindProxyForURL(url, host); }",
        "",
    ))


def full_pac(ai_after_return=False):
    head = "\n".join((
        'var pac_mode = "full";',
        'var pac_full_route = "SOCKS5 127.0.0.1:1370";',
        "function FindProxyForURL(url, host) {",
        '    if (matchDomain(exclude, host) || matchDomain(user_direct, host) || isLocalDirect(host)) return "DIRECT";',
    ))
    ai = '    if (matchDomain(ai_apps, host)) return "PROXY 127.0.0.1:1371";'
    tail = "\n".join((
        "function FindProxyForURLEx(url, host) { return FindProxyForURL(url, host); }",
        "",
    ))
    if ai_after_return:
        return "\n".join((head, "    return pac_full_route;", ai, "}", tail))
    return "\n".join((head, ai, "    return pac_full_route;", "}", tail))


class SpecFileTests(unittest.TestCase):
    def test_shipped_spec_matches_route_lab_template(self):
        shipped = json.loads(SHIPPED.read_text(encoding="utf-8"))
        template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(template, shipped)

    def test_spec_is_valid(self):
        data = spec.load()
        self.assertEqual([], spec.validate(data))
        self.assertEqual(24, len(data["nodes"]))
        self.assertEqual(33, len(data["edges"]))
        self.assertEqual("kaliopa-clean", data["name"])

    def test_required_ports_are_present(self):
        data = spec.load()
        nodes = {node["id"]: node for node in data["nodes"]}
        for node_id, port in spec.REQUIRED_PORTS.items():
            self.assertEqual(port, nodes[node_id]["port"], node_id)

    def test_spec_path_resolves(self):
        self.assertTrue(spec.spec_path().endswith(spec.SPEC_FILENAME))

    def test_dangling_edge_is_reported(self):
        data = copy.deepcopy(spec.load())
        data["edges"][0]["to"] = "ghost"
        issues = spec.validate(data)
        self.assertTrue(any("ghost" in issue for issue in issues))

    def test_wrong_slot_port_is_reported(self):
        data = copy.deepcopy(spec.load())
        for node in data["nodes"]:
            if node["id"] == "warp":
                node["port"] = "9999"
        issues = spec.validate(data)
        self.assertTrue(any("warp" in issue for issue in issues))

    def test_build_ships_the_spec_and_module(self):
        text = (BASE / "Inno.py").read_text(encoding="utf-8")
        self.assertIn("nova_route_spec.json", text)
        self.assertIn("--hidden-import=nova_route_spec", text)

    def test_snapshot_updates_program_copy(self):
        text = (BASE / "tools" / "route-editor" / "snapshot.py").read_text(encoding="utf-8")
        self.assertIn("RESOURCE_SPEC", text)


class PacModeTests(unittest.TestCase):
    def test_hybrid_pac_is_ok(self):
        self.assertEqual([], spec.pac_issues(hybrid_pac(), CLEAN_SETTINGS))

    def test_full_pac_is_ok(self):
        self.assertEqual([], spec.pac_issues(full_pac(), CLEAN_SETTINGS))

    def test_hybrid_order_regression_is_reported(self):
        pac = hybrid_pac().replace(
            '    if (matchDomain(user_direct, host)) return "DIRECT";\n', "")
        pac = pac.replace(
            '    if (isLocalDirect(host)) return "DIRECT";',
            '    if (isLocalDirect(host)) return "DIRECT";\n'
            '    if (matchDomain(user_direct, host)) return "DIRECT";')
        issues = spec.pac_issues(pac, CLEAN_SETTINGS)
        self.assertTrue(any("user_direct" in issue for issue in issues))

    def test_full_ai_after_return_is_reported(self):
        issues = spec.pac_issues(full_pac(ai_after_return=True), CLEAN_SETTINGS)
        self.assertTrue(any("ai_apps" in issue for issue in issues))

    def test_missing_ex_function_is_reported(self):
        pac = hybrid_pac().replace(
            "function FindProxyForURLEx(url, host) { return FindProxyForURL(url, host); }", "")
        issues = spec.pac_issues(pac, CLEAN_SETTINGS)
        self.assertTrue(any("FindProxyForURLEx" in issue for issue in issues))

    def test_unknown_mode_is_reported(self):
        issues = spec.pac_issues(hybrid_pac().replace('"hybrid"', '"weird"'), CLEAN_SETTINGS)
        self.assertTrue(any("режим PAC" in issue for issue in issues))

    def test_reserve_port_is_reported_for_opera(self):
        pac = hybrid_pac() + '\nvar dead = "SOCKS5 127.0.0.1:1375";'
        issues = spec.pac_issues(pac, CLEAN_SETTINGS)
        self.assertTrue(any("1375" in issue for issue in issues))

    def test_reserve_port_is_allowed_for_tor(self):
        pac = hybrid_pac() + '\nvar dead = "SOCKS5 127.0.0.1:1375";'
        settings = {"secondary": {"mode": "tor"}}
        self.assertEqual([], spec.pac_issues(pac, settings))


class SettingsTests(unittest.TestCase):
    def test_clean_settings_match(self):
        self.assertEqual([], spec.settings_issues(CLEAN_SETTINGS))

    def test_full_pac_browser_mode_is_reported(self):
        settings = copy.deepcopy(CLEAN_SETTINGS)
        settings["routes"]["browser"] = "warp"
        issues = spec.settings_issues(settings)
        self.assertTrue(any("routes.browser" in issue for issue in issues))

    def test_empty_settings_are_not_reported(self):
        self.assertEqual([], spec.settings_issues({}))
        self.assertEqual([], spec.settings_issues(None))


if __name__ == "__main__":
    unittest.main()
