"""`pcs` (pinnedPeerCertSha256) не должен убивать живой VLESS-узел.

Ссылка вида `…&sni=cdn.akamai.steamstatic.com&pcs=CD6E…` пинит сертификат одного края CDN; когда
край отдаёт другой сертификат (или пин снят с чужого `sni`), Xray отвечает
`peer cert is unrecognized (against pinnedPeerCertSha256)` и соединения нет. Проверка по
`serverName` уже покрывает TLS, поэтому пин применяется только по `NOVA_VLESS_HONOR_PCS=1`.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_vless  # noqa: E402

PIN = "CD6E838B9BFE31CAB8B3D5C858B0D6223FE84ECE236C1FDB281BE93C302E1E6E"
URI = (
    "vless://780aa2f6-1a02-4fa2-bcd0-fa7d469bdff7@146.75.57.238:443"
    "?type=ws&security=tls&encryption=none&sni=cdn.akamai.steamstatic.com"
    f"&host=example.fastly.net&pcs={PIN}#US"
)


def tls_settings(cfg):
    return cfg["outbounds"][0]["streamSettings"]["tlsSettings"]


class VlessPinnedCertTests(unittest.TestCase):
    def test_pin_is_ignored_by_default(self):
        cfg = nova_vless.build_xray_config(nova_vless.parse_uri(URI), 1370)
        self.assertNotIn("pinnedPeerCertSha256", tls_settings(cfg))
        self.assertEqual("cdn.akamai.steamstatic.com", tls_settings(cfg)["serverName"])

    def test_pin_is_kept_when_explicitly_requested(self):
        with mock.patch.dict(os.environ, {"NOVA_VLESS_HONOR_PCS": "1"}):
            cfg = nova_vless.build_xray_config(nova_vless.parse_uri(URI), 1370)
        self.assertEqual(PIN, tls_settings(cfg)["pinnedPeerCertSha256"])

    def test_link_without_pin_is_unaffected(self):
        uri = URI.split("&pcs=")[0]
        cfg = nova_vless.build_xray_config(nova_vless.parse_uri(uri), 1370)
        self.assertNotIn("pinnedPeerCertSha256", json.dumps(tls_settings(cfg)))


if __name__ == "__main__":
    unittest.main()
