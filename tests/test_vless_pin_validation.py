"""Импорт VLESS: узел с пином на чужой хост отбраковывается сразу.

Замерено 2026-11-01 на публичных узлах: `sni=firefox.com`, `host=…fastly.net`,
`pcs` от третьего сертификата. Xray с таким узлом падает на TLS в любом варианте
конфига (пин / verifyPeerCertByName / serverName=host), поэтому держать его в
списке — 12 секунд ожидания на каждую попытку.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_vless  # noqa: E402

BASE = (
    "vless://780aa2f6-1a02-4fa2-bcd0-fa7d469bdff7@146.75.59.186:443"
    "?type=ws&security=tls&encryption=none&sni={sni}&host={host}{pcs}"
)


def node(sni, host, pcs="&pcs=CD6E838B9BFE31CAB8B3D5C858B0D6223FE84ECE236C1FDB281BE93C302E1E6E"):
    return nova_vless.parse_uri(BASE.format(sni=sni, host=host, pcs=pcs))


class PinConsistencyTests(unittest.TestCase):
    def test_mismatched_pin_is_rejected(self):
        reason = nova_vless.validate(node("firefox.com", "copy.fastly.net"))
        self.assertIn("pcs", reason)

    def test_matching_host_is_accepted(self):
        self.assertEqual("", nova_vless.validate(node("cdn.fastly.net", "cdn.fastly.net")))

    def test_no_pin_is_untouched(self):
        self.assertEqual("", nova_vless.validate(node("firefox.com", "copy.fastly.net", pcs="")))


if __name__ == "__main__":
    unittest.main()
