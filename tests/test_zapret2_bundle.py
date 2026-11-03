"""Вендорный zapret2 (winws2 + Lua) закреплён по версии.

zapret2 — отдельный движок: другой CLI, стратегии на Lua. Он пока не участвует в
маршрутизации, но нужен для UDP-узла (WireGuard/QUIC) и mtproto-фильтра. Чтобы
случайная подмена бинарника или библиотеки не прошла незамеченной, фиксируем
sha256 того, что лежит в `bin/zapret2` (сборка win-bundle от 27.10.2026).

Если обновляем осознанно — меняем константы вместе с файлами и прогоняем
`blockcheck2`/живые пробы.
"""

import hashlib
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DIR = BASE_DIR / "bin" / "zapret2"

EXPECTED = {
    "winws2.exe": ("BA4CECCDEA3576DA0A0991A50D7893EA911DE197281338132DBEC02A5B2FCF58", 656384),
    "lua/zapret-lib.lua": ("6BF528FEF1F0FC3C65E189216FC8A06BB873F6E25D1C29D2BFA4695A09B73440", 93714),
    "lua/zapret-antidpi.lua": ("6D1FA9168E5DE1682FEF91FD174F68B58C50F6739EF00F42CA7DB2B940B6246D", 51866),
}
REQUIRED_LUA = (
    "zapret-lib.lua",
    "zapret-antidpi.lua",
    "zapret-auto.lua",
    "zapret-obfs.lua",
    "zapret-pcap.lua",
    "zapret-tests.lua",
)


class Zapret2BundleTests(unittest.TestCase):
    def setUp(self):
        if not DIR.is_dir():
            self.skipTest("bin/zapret2 отсутствует (bin/ не коммитится)")

    def test_pinned_files_match(self):
        for rel, (expected_hash, expected_size) in EXPECTED.items():
            path = DIR / rel
            self.assertTrue(path.is_file(), f"нет файла {rel}")
            data = path.read_bytes()
            self.assertEqual(expected_size, len(data), rel)
            self.assertEqual(expected_hash.lower(), hashlib.sha256(data).hexdigest(), rel)

    def test_all_lua_libraries_present(self):
        for name in REQUIRED_LUA:
            self.assertTrue((DIR / "lua" / name).is_file(), f"нет lua/{name}")

    def test_presets_shipped(self):
        for name in ("preset2_example.cmd", "preset2_wireguard.cmd"):
            self.assertTrue((DIR / name).is_file(), f"нет {name}")

    def test_winws2_advertises_mtproto_filter(self):
        # Встроенный help/строки winws2: движок умеет --filter-l7=mtproto и
        # mtproto_initial. Это проверка возможностей, а не запуск WinDivert:
        # сам winws2 требует прав администратора.
        data = (DIR / "winws2.exe").read_bytes()
        self.assertIn(b"mtproto_initial", data)
        self.assertIn(b"--filter-l7", data)


if __name__ == "__main__":
    unittest.main()
