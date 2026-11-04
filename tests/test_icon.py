"""Иконка KALIOPA: multi-size ICO и PNG-превью из Route Lab-марки."""

import unittest
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parents[1]


class IconTests(unittest.TestCase):
    def test_ico_has_windows_sizes(self):
        path = BASE / "icon.ico"
        self.assertTrue(path.is_file())
        image = Image.open(path)
        self.assertEqual("ICO", image.format)
        sizes = set(image.info.get("sizes") or [])
        for size in ((16, 16), (32, 32), (48, 48), (256, 256)):
            self.assertIn(size, sizes)

    def test_png_preview_exists(self):
        path = BASE / "docs" / "assets" / "kaliopa-icon.png"
        self.assertTrue(path.is_file())
        self.assertEqual((256, 256), Image.open(path).size)


if __name__ == "__main__":
    unittest.main()
