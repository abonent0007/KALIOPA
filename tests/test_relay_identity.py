"""Опознание релея не должно зависеть от версии форка.

`profiles/opera_relay.key` выпущен для upstream 1.43.2, и релей проверяет логин
`nova-pc-<version>` вместе с ключом. Пока логин собирался из `CURRENT_VERSION`,
любой бамп форка (`1.43.2.4`, `1.43.2.5`, ...) давал 407 `outdated-client`, и
профили WARP/MASQUE/Opera переставали обновляться. Тест фиксирует, что логин
по-прежнему берётся из `API_RELAY_KEY_VERSION`.
"""

import re
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
NOVA_PY = (BASE_DIR / "nova.pyw").read_text(encoding="utf-8", errors="ignore")


class RelayIdentityTests(unittest.TestCase):
    def test_relay_key_version_is_pinned_to_upstream_key(self):
        match = re.search(r'API_RELAY_KEY_VERSION = "([^"]+)"', NOVA_PY)
        self.assertIsNotNone(match, "API_RELAY_KEY_VERSION пропал из nova.pyw")
        self.assertEqual("1.43.2", match.group(1))

    def test_relay_login_uses_pinned_version(self):
        start = NOVA_PY.find("def api_relay_user(")
        self.assertGreater(start, 0, "api_relay_user не найден")
        body = NOVA_PY[start : start + 1200]
        self.assertIn("API_RELAY_KEY_VERSION", body)
        # CURRENT_VERSION допустим только как аварийный fallback, не как источник.
        first_use = body.find("API_RELAY_KEY_VERSION")
        fallback_use = body.find("CURRENT_VERSION")
        self.assertTrue(
            fallback_use == -1 or fallback_use > first_use,
            "CURRENT_VERSION должен использоваться только после API_RELAY_KEY_VERSION",
        )

    def test_fork_version_keeps_upstream_prefix(self):
        sys_path_version = re.search(
            r'CURRENT_VERSION = "([^"]+)"',
            (BASE_DIR / "resources" / "nova_metadata.py").read_text(encoding="utf-8"),
        ).group(1)
        relay_version = re.search(r'API_RELAY_KEY_VERSION = "([^"]+)"', NOVA_PY).group(1)
        self.assertTrue(
            sys_path_version.startswith(relay_version + "."),
            "версия форка должна быть <upstream-relay-version>.N",
        )


if __name__ == "__main__":
    unittest.main()
