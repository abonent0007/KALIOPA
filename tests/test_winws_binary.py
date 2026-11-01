"""Движок winws закреплён на v72.13: случайный откат не должен проходить молча.

27.10.2026 `bin/winws.exe` незаметно оказался сборкой v72.12 из
`bol-van/zapret-win-bundle` (PE 2026-03-12) вместо нашей v72.13 (PE 2026-07-21).
Файл одного размера и без версии в ресурсах, поэтому подмена не видна ни в
сборке, ни в логе — только по sha256.

Если движок обновляется осознанно, обновите `EXPECTED_WINWS_SHA256` и дату,
предварительно прогнав живые пробы стратегий.
"""

import hashlib
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
WINWS = BASE_DIR / "bin" / "winws.exe"
EXPECTED_WINWS_SHA256 = "A14BFF1DF6234EA555D2E0C61B589F0707C0B12D6C9B7EECCDA76012154996E8"
EXPECTED_SIZE = 223232


class WinwsBinaryTests(unittest.TestCase):
    def test_winws_is_the_pinned_build(self):
        if not WINWS.is_file():
            self.skipTest("bin/winws.exe отсутствует (не собран для этой машины)")
        data = WINWS.read_bytes()
        self.assertEqual(EXPECTED_SIZE, len(data))
        self.assertEqual(EXPECTED_WINWS_SHA256.lower(), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
