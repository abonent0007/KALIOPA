"""3x-ui / Xray-JSON подписка: плоский `settings` и `vnext`, без чужих inbound/routing.

`/subJsonPath` 3x-ui отдаёт полный конфиг Xray: `protocol: vless` и
`settings: {address, port, id}`, а не sing-box `type/server`. Проверяем, что
импорт берёт только proxy-outbound, не тащит серверный routing/DNS и умеет
REALITY/XHTTP/WS.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import base64
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_vless  # noqa: E402

UUID = "11111111-1111-1111-1111-111111111111"
REALITY_UUID = "22222222-2222-2222-2222-222222222222"
PBK = "A" * 43
MLDSA = base64.urlsafe_b64encode(b"V" * 1952).decode("ascii").rstrip("=")
BIN = Path(__file__).resolve().parents[1] / "bin" / "nova-xray.exe"


def flat_config():
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{"tag": "socks-in", "listen": "127.0.0.1", "port": 10808,
                      "protocol": "socks", "settings": {"auth": "noauth"}}],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {"address": "edge.example", "port": 443, "id": UUID,
                             "encryption": "none", "level": 8},
                "streamSettings": {
                    "network": "ws",
                    "security": "tls",
                    "tlsSettings": {"serverName": "edge.example", "fingerprint": "chrome"},
                    "wsSettings": {"path": "/ws", "host": "cdn.example", "heartbeatPeriod": 25},
                },
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {"rules": [{"type": "field", "outboundTag": "direct",
                               "domain": ["example.org"]}]},
        "dns": {"servers": ["1.1.1.1"]},
    }


def reality_config():
    return {
        "outbounds": [{
            "tag": "proxy",
            "protocol": "vless",
            "settings": {"vnext": [{
                "address": "reality.example",
                "port": 8443,
                "users": [{"id": REALITY_UUID, "flow": "xtls-rprx-vision",
                           "encryption": "none"}],
            }]},
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "serverNames": ["www.example.com"],
                    "shortIds": ["0123"],
                    "settings": {"publicKey": PBK, "fingerprint": "chrome",
                                 "spiderX": "/", "mldsa65Verify": MLDSA},
                },
            },
        }],
    }


class XrayJsonTests(unittest.TestCase):
    def test_flat_3xui_outbound(self):
        nodes, stats = nova_vless.parse_many(json.dumps(flat_config()))
        self.assertEqual(1, len(nodes))
        self.assertEqual(1, stats["xray_json"])
        self.assertEqual(0, stats["other_scheme"])
        node = nodes[0]
        self.assertEqual("edge.example", node.host)
        self.assertEqual(443, node.port)
        self.assertEqual("ws", node.network)
        self.assertEqual("tls", node.security)
        self.assertEqual("/ws", node.path)
        self.assertEqual("cdn.example", node.host_header)
        self.assertEqual("25", node.extra["eh"])

    def test_inbound_and_routing_are_not_imported(self):
        node = nova_vless.parse_xray_json(json.dumps(flat_config()))[0]
        cfg = nova_vless.build_xray_config(node, 1370)
        self.assertEqual([1370], [item["port"] for item in cfg["inbounds"]])
        self.assertNotIn("routing", cfg)
        self.assertNotIn("dns", cfg)

    def test_reality_vnext_with_nested_settings(self):
        nodes = nova_vless.parse_xray_json(json.dumps(reality_config()))
        self.assertEqual(1, len(nodes))
        node = nodes[0]
        self.assertEqual("reality", node.security)
        self.assertEqual("www.example.com", node.sni)
        self.assertEqual(PBK, node.reality_public_key)
        self.assertEqual("0123", node.reality_short_id)
        self.assertEqual("/", node.reality_spider_x)
        self.assertEqual("xtls-rprx-vision", node.flow)
        cfg = nova_vless.build_xray_config(node, 1370)
        reality = cfg["outbounds"][0]["streamSettings"]["realitySettings"]
        self.assertEqual(MLDSA, reality["mldsa65Verify"])

    def test_array_of_configs(self):
        nodes = nova_vless.parse_xray_json(json.dumps([flat_config(), reality_config()]))
        self.assertEqual(2, len(nodes))

    def test_trojan_json_is_imported(self):
        document = {"outbounds": [{"tag": "proxy", "protocol": "trojan",
                                   "settings": {"address": "t.example", "port": 443,
                                                "password": "x"}}]}
        nodes, stats = nova_vless.parse_many(json.dumps(document))
        self.assertEqual(1, len(nodes))
        self.assertEqual("trojan", nodes[0].protocol)
        self.assertEqual(1, stats["trojan"])
        self.assertEqual(0, stats["other_scheme"])

    def test_unknown_protocol_is_counted_not_imported(self):
        document = {"outbounds": [{"tag": "proxy", "protocol": "hysteria2",
                                   "settings": {"address": "h.example", "port": 443}}]}
        nodes, stats = nova_vless.parse_many(json.dumps(document))
        self.assertEqual(0, len(nodes))
        self.assertEqual(1, stats["other_scheme"])

    def test_xhttp_settings_are_preserved(self):
        document = {"outbounds": [{
            "tag": "proxy", "protocol": "vless",
            "settings": {"address": "x.example", "port": 443, "id": UUID,
                         "encryption": "none"},
            "streamSettings": {
                "network": "xhttp",
                "security": "tls",
                "tlsSettings": {"serverName": "x.example"},
                "xhttpSettings": {"path": "/x", "mode": "auto",
                                  "extra": {"xmux": {"maxConcurrency": "8-16"}}},
            },
        }]}
        node = nova_vless.parse_xray_json(json.dumps(document))[0]
        stream = nova_vless.build_xray_config(node, 1370)["outbounds"][0]["streamSettings"]
        self.assertEqual("/x", stream["xhttpSettings"]["path"])
        self.assertEqual("auto", stream["xhttpSettings"]["mode"])
        self.assertEqual({"maxConcurrency": "8-16"},
                         stream["xhttpSettings"]["extra"]["xmux"])


class WebSocketAndTlsParamTests(unittest.TestCase):
    def test_eh_is_converted_to_uint32(self):
        uri = ("vless://%s@example.com:443?type=ws&security=tls&sni=example.com"
               "&path=%%2Fws&eh=30#WS" % UUID)
        cfg = nova_vless.build_xray_config(nova_vless.parse_uri(uri), 1370)
        self.assertEqual(30, cfg["outbounds"][0]["streamSettings"]["wsSettings"]
                         ["heartbeatPeriod"])

    def test_non_numeric_eh_is_dropped(self):
        uri = ("vless://%s@example.com:443?type=ws&security=tls&sni=example.com"
               "&path=%%2Fws&eh=abc#WS" % UUID)
        cfg = nova_vless.build_xray_config(nova_vless.parse_uri(uri), 1370)
        self.assertNotIn("heartbeatPeriod",
                         cfg["outbounds"][0]["streamSettings"]["wsSettings"])

    def test_ech_and_cs_are_opt_in(self):
        uri = ("vless://%s@example.com:443?type=ws&security=tls&sni=example.com"
               "&path=%%2Fws&ech=udp%%3A%%2F%%2F1.1.1.1&cs=TLS_AES_128_GCM_SHA256#TLS"
               % UUID)
        node = nova_vless.parse_uri(uri)
        with mock.patch.dict(os.environ, {"NOVA_VLESS_HONOR_ECH": "0",
                                          "NOVA_VLESS_HONOR_CS": "0"}):
            tls = nova_vless.build_xray_config(node, 1370)["outbounds"][0][
                "streamSettings"]["tlsSettings"]
            self.assertNotIn("echConfigList", tls)
            self.assertNotIn("cipherSuites", tls)
        with mock.patch.dict(os.environ, {"NOVA_VLESS_HONOR_ECH": "1",
                                          "NOVA_VLESS_HONOR_CS": "1"}):
            tls = nova_vless.build_xray_config(node, 1370)["outbounds"][0][
                "streamSettings"]["tlsSettings"]
            self.assertEqual("udp://1.1.1.1", tls["echConfigList"])
            self.assertEqual("TLS_AES_128_GCM_SHA256", tls["cipherSuites"])


@unittest.skipUnless(os.name == "nt" and BIN.is_file(), "nova-xray.exe is not available")
class XrayConfigCheckTests(unittest.TestCase):
    def test_generated_configs_load_in_the_core(self):
        cases = [nova_vless.parse_xray_json(json.dumps(flat_config()))[0],
                 nova_vless.parse_xray_json(json.dumps(reality_config()))[0]]
        with tempfile.TemporaryDirectory(prefix="kaliopa-xray-") as folder:
            for index, node in enumerate(cases):
                cfg = nova_vless.build_xray_config(node, 18080 + index)
                path = os.path.join(folder, "case%d.json" % index)
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(cfg, handle, ensure_ascii=False, indent=2)
                proc = subprocess.run([str(BIN), "check", "--config", path],
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(0, proc.returncode, proc.stderr or proc.stdout)


if __name__ == "__main__":
    unittest.main()
