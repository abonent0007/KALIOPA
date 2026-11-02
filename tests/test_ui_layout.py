"""Вписывание фона в окно: кнопки считаются от углов картинки, а не окна."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_ui_layout as layout  # noqa: E402


class ContainRectTests(unittest.TestCase):
    def test_same_aspect_fills_the_window(self):
        self.assertEqual((0, 0, 360, 270), layout.contain_rect(720, 540, 360, 270))

    def test_wider_image_gets_bars_top_and_bottom(self):
        x, y, width, height = layout.contain_rect(967, 540, 360, 270)
        self.assertEqual(360, width)
        self.assertEqual(201, height)
        self.assertEqual(0, x)
        self.assertEqual(34, y)

    def test_taller_image_gets_bars_left_and_right(self):
        x, y, width, height = layout.contain_rect(540, 720, 360, 270)
        self.assertEqual(202, width)
        self.assertEqual(270, height)
        self.assertEqual(79, x)
        self.assertEqual(0, y)

    def test_tiny_source_is_still_visible(self):
        x, y, width, height = layout.contain_rect(1, 1, 360, 270)
        self.assertGreaterEqual(min(width, height), 1)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)

    def test_broken_dimensions_do_not_crash(self):
        self.assertEqual((0, 0, 360, 270), layout.contain_rect(0, None, 360, 270))


class CornerPointTests(unittest.TestCase):
    def test_corners_and_center_follow_the_image_rect(self):
        points = layout.corner_points((0, 34, 360, 201), margin=10)
        self.assertEqual(10, points["left"])
        self.assertEqual(350, points["right"])
        self.assertEqual(44, points["top"])
        self.assertEqual(225, points["bottom"])
        self.assertEqual(180, points["center_x"])
        self.assertEqual(134.5, points["center_y"])


if __name__ == "__main__":
    unittest.main()
