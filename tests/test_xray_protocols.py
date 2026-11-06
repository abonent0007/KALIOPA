"""Xray-протоколы кроме VLESS: Trojan, VMess, Shadowsocks.

Ссылки и JSON-подписки 3x-ui теперь дают все четыре протокола, которые умеет
`nova-xray`. Проверяем разбор, сборку outbound, обратимость ссылки и то, что
ядро принимает результат (`nova-xray check`).
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_profiles  # noqa: E402
import nova_subscriptions  # noqa: E402
import nova_vless  # noqa: E402

UUID = "11111111-1111-1111-1111-111111111111"
BIN = Path(__file__).resolve().parents[1] / "bin" / "nova-xray.exe"

TROJAN = ("trojan://p%40ss@t.example:443?type=ws&security=tls&sni=t.example"
          "&host=cdn.example&path=%2Ft#Trojan")
VMESS_OBJECT = {
    "v": "2", "ps": "VMess", "add": "v.example", "port": "443",
    "id": UUID, "aid": "0", "scy": "auto", "net": "ws", "type": "none",
    "host": "cdn.example", "path": "/vm", "tls": "tls", "sni": "v.example",
    "alpn": "h2,http/1.1", "fp": "chrome",
}
VMESS = "vmess://" + base64.b64encode(
    json.dumps(VMESS_OBJECT, ensure_ascii=False).encode("utf-8")).decode("ascii")
SS_TOKEN = base64.urlsafe_b64encode(b"aes-256-gcm:pass:word").decode("ascii").rstrip("=")
SS = "ss://%s@ss.example:8388#Shadowsocks" % SS_TOKEN


class TrojanTests(unittest.TestCase):
    def test_link_and_config(self):
        node = nova_vless.parse_trojan_uri(TROJAN)
        self.assertIsNotNone(node)
        self.assertEqual("trojan", node.protocol)
        self.assertEqual("p@ss", node.password)
        self.assertEqual("ws", node.network)
        self.assertEqual("tls", node.security)
        self.assertEqual("cdn.example", node.host_header)
        self.assertEqual("", nova_vless.validate(node))
        cfg = nova_vless.build_xray_config(node, 1370)
        out = cfg["outbounds"][0]
        self.assertEqual("trojan", out["protocol"])
        self.assertEqual("p@ss", out["settings"]["servers"][0]["password"])

    def test_round_trip(self):
        node = nova_vless.parse_trojan_uri(TROJAN)
        again = nova_vless.parse_link(node.to_uri())
        self.assertEqual(node.identity, again.identity)

    def test_missing_password_is_rejected(self):
        self.assertIsNone(nova_vless.parse_trojan_uri("trojan://@t.example:443#x"))

    def test_flow_is_dropped_because_xray_removed_it(self):
        uri = TROJAN.replace("&path=%2Ft", "&flow=xtls-rprx-vision&path=%2Ft")
        node = nova_vless.parse_trojan_uri(uri)
        self.assertEqual("", node.flow)
        self.assertEqual("", nova_vless.validate(node))
        cfg = nova_vless.build_xray_config(node, 1370)
        self.assertNotIn("flow", cfg["outbounds"][0]["settings"]["servers"][0])


class VmessTests(unittest.TestCase):
    def test_link_and_config(self):
        node = nova_vless.parse_vmess_uri(VMESS)
        self.assertIsNotNone(node)
        self.assertEqual("vmess", node.protocol)
        self.assertEqual(UUID, node.uuid)
        self.assertEqual("auto", node.method)
        self.assertEqual("ws", node.network)
        self.assertEqual("/vm", node.path)
        self.assertEqual("cdn.example", node.host_header)
        self.assertEqual("", nova_vless.validate(node))
        out = nova_vless.build_xray_config(node, 1370)["outbounds"][0]
        self.assertEqual("vmess", out["protocol"])
        user = out["settings"]["vnext"][0]["users"][0]
        self.assertEqual(UUID, user["id"])
        self.assertNotIn("alterId", user)

    def test_round_trip(self):
        node = nova_vless.parse_vmess_uri(VMESS)
        again = nova_vless.parse_link(node.to_uri())
        self.assertEqual(node.identity, again.identity)

    def test_grpc_multi_uses_service_name_and_authority(self):
        obj = dict(VMESS_OBJECT, net="grpc", type="multi", path="svc", host="authority.example")
        token = base64.urlsafe_b64encode(
            json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode("ascii").rstrip("=")
        node = nova_vless.parse_vmess_uri("vmess://" + token)
        self.assertEqual("grpc", node.network)
        self.assertEqual("svc", node.service_name)
        self.assertEqual("authority.example", node.host_header)
        self.assertEqual("multi", node.mode)

    def test_broken_base64_is_rejected(self):
        self.assertIsNone(nova_vless.parse_vmess_uri("vmess://not-base64"))


class ShadowsocksTests(unittest.TestCase):
    def test_sip002_link_and_config(self):
        node = nova_vless.parse_ss_uri(SS)
        self.assertIsNotNone(node)
        self.assertEqual("shadowsocks", node.protocol)
        self.assertEqual("aes-256-gcm", node.method)
        self.assertEqual("pass:word", node.password)
        self.assertEqual("", nova_vless.validate(node))
        out = nova_vless.build_xray_config(node, 1370)["outbounds"][0]
        self.assertEqual("shadowsocks", out["protocol"])
        server = out["settings"]["servers"][0]
        self.assertEqual("aes-256-gcm", server["method"])
        self.assertEqual("pass:word", server["password"])

    def test_legacy_fully_encoded_link(self):
        token = base64.b64encode(b"aes-128-gcm:secret@legacy.example:8388").decode("ascii")
        node = nova_vless.parse_ss_uri("ss://" + token + "#legacy")
        self.assertIsNotNone(node)
        self.assertEqual("legacy.example", node.host)
        self.assertEqual("secret", node.password)

    def test_plain_userinfo_link(self):
        node = nova_vless.parse_ss_uri("ss://aes-128-gcm:secret@plain.example:8388#plain")
        self.assertIsNotNone(node)
        self.assertEqual("aes-128-gcm", node.method)
        self.assertEqual("secret", node.password)

    def test_plugin_link_is_refused(self):
        self.assertIsNone(nova_vless.parse_ss_uri(
            "ss://aes-128-gcm:secret@plain.example:8388?plugin=obfs-local#p"))

    def test_round_trip(self):
        node = nova_vless.parse_ss_uri(SS)
        again = nova_vless.parse_link(node.to_uri())
        self.assertEqual(node.identity, again.identity)


class MixedSubscriptionTests(unittest.TestCase):
    def test_all_schemes_are_counted(self):
        text = "\n".join([TROJAN, VMESS, SS,
                          "vless://%s@v.example:443?type=tcp&security=tls&sni=v.example#V" % UUID,
                          "hysteria2://x@h.example:443#H"])
        nodes, stats = nova_vless.parse_many(text)
        self.assertEqual({"vless", "trojan", "vmess", "shadowsocks"},
                         {node.protocol for node in nodes})
        self.assertEqual(1, stats["other_scheme"])
        self.assertEqual(0, stats["bad"])

    def test_paste_import_finds_all_four(self):
        candidates = nova_profiles.parse_import_text("\n".join([TROJAN, VMESS, SS]), "mix")
        self.assertEqual(3, len(candidates))
        self.assertTrue(all(c["ok"] for c in candidates))
        protocols = set()
        for candidate in candidates:
            node, issues = nova_profiles.parse_vless_profile(json.loads(candidate["text"]))
            self.assertEqual([], issues)
            protocols.add(node.protocol)
        self.assertEqual({"trojan", "vmess", "shadowsocks"}, protocols)

    def test_vless_identity_is_unchanged(self):
        # The VLESS key is how existing profiles are recognised; changing it
        # would make every subscription look replaced after an upgrade.
        uri = "vless://%s@v.example:443?type=ws&security=tls&sni=v.example#V" % UUID
        node = nova_vless.parse_uri(uri)
        self.assertEqual(
            "%s|v.example|443|encryption=none|security=tls|sni=v.example|type=ws" %
            UUID, node.identity)


class ProfileStorageTests(unittest.TestCase):
    def test_import_and_list_all_protocols(self):
        base = tempfile.mkdtemp(prefix="kaliopa-profiles-")
        candidates = nova_profiles.parse_import_text("\n".join([TROJAN, VMESS, SS]), "mix")
        results = nova_profiles.import_candidates(base, candidates)
        self.assertEqual(3, sum(1 for item in results if item.get("status") == "imported"))
        listed = [item for item in nova_profiles.list_profiles(base)
                  if item.get("kind") == nova_profiles.KIND_VLESS]
        self.assertEqual(3, len(listed))
        protocols = set()
        for record in listed:
            node = nova_profiles.vless_node_of_record(record)
            self.assertIsNotNone(node)
            protocols.add(node.protocol)
        self.assertEqual({"trojan", "vmess", "shadowsocks"}, protocols)


class SubscriptionImportTests(unittest.TestCase):
    def test_refresh_imports_a_mixed_list(self):
        base = tempfile.mkdtemp(prefix="kaliopa-sub-mixed-")
        body = "\n".join([TROJAN, VMESS, SS,
                          "vless://%s@v.example:443?type=tcp&security=tls&sni=v.example#V" % UUID
                          ]).encode("utf-8")
        record = nova_subscriptions.normalize_record({
            "url": "https://example.com/sub", "kind": "vless", "shape": nova_subscriptions._SHAPE,
            "interval_hours": 12, "keep": 20,
        })
        result = nova_subscriptions.FetchResult("ok", body=body, size=len(body))
        with mock.patch.object(nova_subscriptions, "_probed_add_identities",
                               side_effect=lambda add, _by, _say, _title: add):
            outcome, after, stats = nova_subscriptions.refresh(
                base, record, fetcher=lambda *args, **kwargs: result, now=1000)
        self.assertEqual("updated", outcome)
        self.assertEqual(4, after["node_count"])
        self.assertEqual(1, stats["trojan"])
        self.assertEqual(1, stats["vmess"])
        self.assertEqual(1, stats["shadowsocks"])
        self.assertEqual(4, len(nova_profiles.list_profiles(base)))


class XrayJsonProtocolTests(unittest.TestCase):
    def test_trojan_vmess_shadowsocks_json(self):
        document = {"outbounds": [
            {"tag": "proxy", "protocol": "trojan",
             "settings": {"address": "t.example", "port": 443, "password": "p"},
             "streamSettings": {"network": "ws", "security": "tls",
                                "tlsSettings": {"serverName": "t.example"},
                                "wsSettings": {"path": "/t"}}},
            {"tag": "proxy", "protocol": "vmess",
             "settings": {"address": "v.example", "port": 443, "id": UUID,
                          "security": "auto"},
             "streamSettings": {"network": "ws", "security": "tls",
                                "tlsSettings": {"serverName": "v.example"},
                                "wsSettings": {"path": "/v"}}},
            {"tag": "proxy", "protocol": "shadowsocks",
             "settings": {"address": "s.example", "port": 8388,
                          "method": "aes-256-gcm", "password": "p"}},
        ]}
        nodes = nova_vless.parse_xray_json(json.dumps(document))
        self.assertEqual({"trojan", "vmess", "shadowsocks"},
                         {node.protocol for node in nodes})


    def test_shadowsocks_json_plugin_is_skipped(self):
        document = {"outbounds": [{
            "tag": "proxy", "protocol": "shadowsocks",
            "settings": {"address": "s.example", "port": 8388,
                         "method": "aes-256-gcm", "password": "p",
                         "plugin": "obfs-local"},
        }]}
        nodes = nova_vless.parse_xray_json(json.dumps(document))
        self.assertEqual([], nodes)


@unittest.skipUnless(os.name == "nt" and BIN.is_file(), "nova-xray.exe is not available")
class CoreAcceptsProtocolsTests(unittest.TestCase):
    def test_generated_configs_load_in_the_core(self):
        nodes = [nova_vless.parse_link(TROJAN), nova_vless.parse_link(VMESS),
                 nova_vless.parse_link(SS)]
        with tempfile.TemporaryDirectory(prefix="kaliopa-xray-proto-") as folder:
            for index, node in enumerate(nodes):
                cfg = nova_vless.build_xray_config(node, 18090 + index)
                path = os.path.join(folder, "case%d.json" % index)
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(cfg, handle, ensure_ascii=False, indent=2)
                proc = subprocess.run([str(BIN), "check", "--config", path],
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(0, proc.returncode,
                                 "%s: %s" % (node.protocol, proc.stderr or proc.stdout))


if __name__ == "__main__":
    unittest.main()
