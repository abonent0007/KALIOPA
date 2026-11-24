"""Диспетчер действий окна «Профили»: у каждого действия должен быть метод.

Регрессия 2026-11-24: в словаре обработчиков стоял несуществующий
`_on_dns_test_selected`, и попытка собрать словарь роняла любую кнопку действия
(`AttributeError`), включая «Настройки…» у Custom AWG.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_profiles_ui as ui  # noqa: E402


class ActionWiringTests(unittest.TestCase):
    def test_every_tab_action_has_a_label(self):
        for key, rows in ui.TAB_ACTION_ROWS.items():
            self.assertIn(key, dict(ui.TABS), f"вкладка {key!r} без подписи")
            for row in rows:
                for action in row:
                    self.assertIn(action, ui.ACTION_LABELS,
                                  f"действие {action!r} без подписи")

    def test_every_action_has_a_handler(self):
        for key, rows in ui.TAB_ACTION_ROWS.items():
            for row in rows:
                for action in row:
                    if action in ui._ACTION_JOBS:
                        continue
                    method = ui._ACTION_METHODS.get(action)
                    self.assertIsNotNone(method,
                                         f"действие {action!r} без метода")
                    self.assertTrue(hasattr(ui.ProfilesWindow, method),
                                    f"у окна нет метода {method!r} для {action!r}")

    def test_dns_actions_are_wired(self):
        for action in ("dns_test", "dns_test_all", "dns_apply", "dns_reset"):
            self.assertIn(action, ui.ACTION_LABELS)
            self.assertTrue(hasattr(ui.ProfilesWindow, ui._ACTION_METHODS[action]))

    def test_dispatch_of_unknown_action_is_a_no_op(self):
        class Fake:
            alive = lambda self: True  # noqa: E731

            def _report_error(self, *a, **k):  # pragma: no cover - не должно вызываться
                raise AssertionError("unknown action reported an error")

        fake = Fake()
        ui.ProfilesWindow._dispatch_action(fake, "no-such-action")


if __name__ == "__main__":
    unittest.main()
