"""Окно профилей: кэш файловой половины снимка.

Окно обновляется каждые 1.5 с, но 550–900 профилей, `profile-stats.json` и
`subscriptions.json` меняются только при записи. Сигнатура по mtime/size
позволяет не перечитывать их на каждом тике, сохраняя свежесть после
добавления/удаления/переименования профиля.
"""

import os
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_profiles  # noqa: E402
import nova_profiles_ui as ui  # noqa: E402
import nova_subscriptions  # noqa: E402


class ProfileTreeSignatureTests(unittest.TestCase):
    def setUp(self):
        self.base = pathlib.Path(tempfile.mkdtemp(prefix="kaliopa-cache-"))
        profiles = self.base / "profiles"
        for group in nova_profiles.GROUPS:
            (profiles / group).mkdir(parents=True, exist_ok=True)
        (profiles / "profile-stats.json").write_text("{}", encoding="utf-8")
        (profiles / "profile-selection.json").write_text('{"version":1,"mode":"auto"}',
                                                         encoding="utf-8")
        stats_path = pathlib.Path(nova_profiles.stats_path(str(self.base)))
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text("{}", encoding="utf-8")
        selection_path = pathlib.Path(nova_profiles.selection_path(str(self.base)))
        selection_path.parent.mkdir(parents=True, exist_ok=True)
        selection_path.write_text('{"version":1,"mode":"auto"}', encoding="utf-8")
        (profiles / "subscriptions.json").write_text('{"subscriptions":[]}', encoding="utf-8")

    def signature(self):
        return ui.ProfilesWindow._profile_tree_signature(
            str(self.base), nova_profiles, nova_subscriptions)

    def test_unchanged_tree_keeps_the_same_signature(self):
        self.assertEqual(self.signature(), self.signature())

    def test_new_profile_file_changes_it(self):
        before = self.signature()
        target = self.base / "profiles" / nova_profiles.GROUP_VLESS / "node.json"
        target.write_text('{"type":"vless","uri":"vless://x"}', encoding="utf-8")
        # Directory mtime can be coarse or equal to the setup timestamp; force a distinct value.
        stamp = time.time() + 2
        os.utime(target.parent, (stamp, stamp))
        self.assertNotEqual(before, self.signature())

    def test_stats_or_subscriptions_edit_changes_it(self):
        before = self.signature()
        stats = pathlib.Path(nova_profiles.stats_path(str(self.base)))
        stats.write_text('{"x":{"ok":1}}', encoding="utf-8")
        stamp = time.time() + 2
        os.utime(stats, (stamp, stamp))
        self.assertNotEqual(before, self.signature())
        before = self.signature()
        subs = self.base / "profiles" / "subscriptions.json"
        subs.write_text('{"subscriptions":[{"url":"https://example.com"}]}', encoding="utf-8")
        stamp = time.time() + 4
        os.utime(subs, (stamp, stamp))
        self.assertNotEqual(before, self.signature())


class ReserveSourceTests(unittest.TestCase):
    def test_public_reserve_sources_are_registered(self):
        urls = {str(item.get("url")) for item in nova_subscriptions.DEFAULT_SOURCES}
        self.assertTrue(any("vpn-free-russia/main/verified_configs.txt" in url for url in urls))
        self.assertTrue(any("vpn-free-russia/main/ru_configs.txt" in url for url in urls))
        self.assertGreaterEqual(nova_subscriptions.MAX_TOTAL_VLESS, 900)


if __name__ == "__main__":
    unittest.main()
