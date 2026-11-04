"""Route Lab: страница, API и ассеты на месте, пресеты не потеряны."""

import json
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "tools" / "route-editor"


class RouteEditorTests(unittest.TestCase):
    def test_page_and_assets_exist(self):
        for name in ("index.php", "assets/app.css", "assets/app.js", "README.md"):
            self.assertTrue((BASE / name).is_file(), name)

    def test_php_api_actions_are_declared(self):
        text = (BASE / "index.php").read_text(encoding="utf-8")
        for action in ("list", "load", "save", "delete"):
            self.assertIn("'%s'" % action, text)
        self.assertIn("function k_graph_error", text)
        self.assertIn("routes", text)

    def test_js_has_real_kaliopa_presets(self):
        text = (BASE / "assets/app.js").read_text(encoding="utf-8")
        for preset in ("current", "browser", "telegram", "vless", "blank"):
            self.assertIn("%s:" % preset, text)
        self.assertIn("127.0.0.1:1370", text)
        self.assertIn("127.0.0.1:1371", text)
        self.assertIn("127.0.0.1:1372", text)

    def test_routes_storage_is_not_committed(self):
        ignore = (BASE / "routes" / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.json", ignore)

    def test_default_kaliopa_template_is_configured(self):
        template = json.loads((BASE / "templates" / "kaliopa-clean.json").read_text(encoding="utf-8"))
        self.assertEqual("kaliopa-clean", template["name"])
        self.assertEqual(24, len(template["nodes"]))
        self.assertEqual(29, len(template["edges"]))
        node_ids = {node["id"] for node in template["nodes"]}
        for required in ("pac", "warp", "opera", "relay", "dns", "proton", "cf_awg", "tor", "xray"):
            self.assertIn(required, node_ids)


if __name__ == "__main__":
    unittest.main()
