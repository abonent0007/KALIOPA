"""Google AI-хосты должны уходить в зарубежный слот, а не в RU-выход.

`list/second.txt` содержит только родительский `gemini.google`, а `matchDomain`
в PAC не считает родителя покрытием `.com`-хоста. Из-за этого
`gemini.google.com` попадал в `foreign_default` (основной RU-выход), и Google
показывал «Gemini не поддерживается в вашей стране». Тест держит список
точных хостов и его проводку в `ai_second`.
"""

import re
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "resources"))

from nova_routing_profiles import AI_APP_DOMAINS, choose_ai_primary_route  # noqa: E402

NOVA_PY = (BASE_DIR / "nova.pyw").read_text(encoding="utf-8", errors="ignore")
AI_LIST = {
    line.strip().lower()
    for line in (BASE_DIR / "list" / "ai.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}

REQUIRED = {"gemini.google.com", "aistudio.google.com", "ai.google.dev"}


def google_ai_hosts():
    start = NOVA_PY.find("_google_ai_hosts = {")
    if start < 0:
        return set()
    end = NOVA_PY.find("}", start)
    return set(re.findall(r'"([^"]+)"', NOVA_PY[start:end]))


class AIRoutingTests(unittest.TestCase):
    def test_google_ai_hosts_block_exists(self):
        self.assertTrue(google_ai_hosts(), "_google_ai_hosts пропал из generate_pac")

    def test_required_hosts_are_listed(self):
        missing = REQUIRED - google_ai_hosts()
        self.assertEqual(set(), missing, "Google AI-хосты выпали из точечного списка")

    def test_hosts_exist_in_ai_list(self):
        missing = google_ai_hosts() - AI_LIST
        self.assertEqual(set(), missing, "хосты точечного списка отсутствуют в list/ai.txt")

    def test_hosts_are_merged_into_ai_second(self):
        self.assertIn("ai_second_domains |= (_ai_set & _google_ai_hosts)", NOVA_PY)

    def test_ai_primary_uses_google_hosts_and_opencode(self):
        self.assertIn("ai_primary_hosts = set(_google_ai_hosts) | {", NOVA_PY)
        self.assertIn('"opencode.ai"', NOVA_PY)
        self.assertIn('"crbug.com"', NOVA_PY)
        self.assertIn('"issues.chromium.org"', NOVA_PY)

    def test_crbug_is_in_ai_apps(self):
        self.assertIn("crbug.com", AI_APP_DOMAINS)
        self.assertIn("issues.chromium.org", AI_APP_DOMAINS)

    def test_ai_primary_rule_precedes_ai_apps(self):
        self.assertLess(
            NOVA_PY.index("matchDomain(ai_primary, host)"),
            NOVA_PY.index("for _list_name, _mode, _route in ("),
        )
        self.assertIn('f\'    if (matchDomain(ai_primary, host)) return "{ai_primary_route}";\\n\'', NOVA_PY)
        self.assertIn("var ai_primary = {ai_primary_js};", NOVA_PY)


class AIPrimaryRouteTests(unittest.TestCase):
    """Google AI/opencode: строка AI (Opera EU .47); primary — если secondary лёг."""

    AI = "PROXY 127.0.0.1:1371"
    PRIMARY = "SOCKS5 127.0.0.1:1370"

    def route(self, mode="opera", active=True, secondary=True):
        return choose_ai_primary_route(mode, self.AI, self.PRIMARY, active, secondary)

    def test_ai_row_is_used_when_secondary_up(self):
        # Opera EU 77.111.244.47 (NL): Gemini и ChatGPT 200 без капчи.
        self.assertEqual(self.AI, self.route())

    def test_secondary_down_uses_primary(self):
        self.assertEqual(self.PRIMARY, self.route(secondary=False))

    def test_secondary_and_primary_down_keeps_ai_row(self):
        self.assertEqual(self.AI, self.route(active=False, secondary=False))

    def test_direct_mode_is_not_overridden(self):
        self.assertEqual("DIRECT", self.route(mode="direct"))

    def test_auto_mode_also_uses_ai_row(self):
        self.assertEqual(self.AI, self.route(mode="auto"))


if __name__ == "__main__":
    unittest.main()
