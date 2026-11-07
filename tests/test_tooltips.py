"""Подсказки кнопок: словарь, эвристики и навешивание на дерево виджетов."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_tooltips  # noqa: E402


class DescribeTests(unittest.TestCase):
    def test_a_known_label_gets_its_own_text(self):
        self.assertIn("Профили", nova_tooltips.describe("Профили"))
        self.assertIn("туннель", nova_tooltips.describe("Проверить").lower())

    def test_an_unknown_label_with_a_known_verb_gets_a_generic_hint(self):
        self.assertIn("Обновить", nova_tooltips.describe("Обновить всё"))

    def test_an_unknown_label_still_explains_itself(self):
        self.assertEqual("Кнопка «Странная кнопка».", nova_tooltips.describe("Странная кнопка"))

    def test_empty_text_has_no_tooltip(self):
        self.assertEqual("", nova_tooltips.describe("   "))


class AttachTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover - no Tk on the machine
            raise unittest.SkipTest(f"tkinter unavailable: {exc}")
        cls.tk = tk
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_buttons_get_hints_and_labels_do_not(self):
        tk = self.tk
        frame = tk.Frame(self.root)
        frame.pack()
        button = tk.Button(frame, text="Проверить список", command=lambda: None)
        button.pack()
        label = tk.Label(frame, text="Проверить список")
        label.pack()
        attached = nova_tooltips.attach_tree(frame)
        self.assertGreaterEqual(attached, 1)
        self.assertTrue(getattr(button, "_nova_tooltip_hint", ""))
        self.assertFalse(getattr(label, "_nova_tooltip_hint", ""))
        self.assertTrue(button.bind("<Enter>"))
        frame.destroy()

    def test_attaching_twice_does_not_duplicate_the_binding(self):
        tk = self.tk
        button = tk.Button(self.root, text="Сохранить", command=lambda: None)
        button.pack()
        self.assertTrue(nova_tooltips.attach(button, "Сохранить настройки."))
        first = button.bind("<Enter>")
        self.assertTrue(nova_tooltips.attach(button, "Сохранить настройки."))
        self.assertEqual(first, button.bind("<Enter>"))
        button.destroy()


if __name__ == "__main__":
    unittest.main()
