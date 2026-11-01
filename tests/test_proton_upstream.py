"""Proton: версия клиента и окно капчи — ровно то, что поменял upstream в 1.44.

Старая версия клиента (`5.4.44.0`) заставляет Proton API отвечать 422/5003, а окно капчи без
`--proxy-server=direct://` наследует системный PAC Nova и уходит другим адресом — Proton
отвечает 12087. Тест держит оба места.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_captcha_window  # noqa: E402
import nova_proton  # noqa: E402


class ProtonClientVersionTests(unittest.TestCase):
    def test_app_version_matches_upstream_1_44(self):
        self.assertEqual("android-vpn@5.20.21.0", nova_proton.APP_VERSION)

    def test_user_agent_matches_app_version(self):
        self.assertEqual("ProtonVPN/5.20.21.0", nova_proton.USER_AGENT_APP)

    def test_api_hosts_stay_the_two_upstream_ones(self):
        self.assertEqual(
            ("https://vpn-api.proton.me", "https://api.protonvpn.ch"),
            tuple(nova_proton.API_HOSTS),
        )


class CaptchaWindowProxyTests(unittest.TestCase):
    def test_direct_switch_is_chromiums_spelling(self):
        self.assertEqual("direct://", nova_captcha_window.DIRECT_BROWSER_PROXY)

    def test_direct_call_does_not_use_a_proxy(self):
        self.assertIsNone(nova_captcha_window.browser_proxy(None))

    def test_http_proxy_is_passed_through(self):
        self.assertEqual(
            "http://127.0.0.1:1371",
            nova_captcha_window.browser_proxy("http://127.0.0.1:1371"),
        )

    def test_proxy_with_credentials_is_not_usable(self):
        # Chromium не принимает логин/пароль в --proxy-server (TLS-релей).
        self.assertIsNone(
            nova_captcha_window.browser_proxy("https://nova-pc-1.43.2:secret@relay.example:8443")
        )


if __name__ == "__main__":
    unittest.main()
