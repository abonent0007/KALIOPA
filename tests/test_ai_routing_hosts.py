"""Google AI-хосты должны уходить в зарубежный слот, а не в RU-выход.

`list/second.txt` содержит только родительский `gemini.google`, а `matchDomain`
в PAC не считает родителя покрытием `.com`-хоста. Из-за этого
`gemini.google.com` попадал в `foreign_default` (основной RU-выход), и Google
показывал «Gemini не поддерживается в вашей стране». Тест держит список
точных хостов и его проводку в `ai_second`.
"""

import re
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
