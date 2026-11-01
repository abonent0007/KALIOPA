"""Локальный DoH-резолвер: сборка запроса, разбор вопроса, fallback."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_doh_resolver as doh  # noqa: E402


class _FakeResponse:
    def __init__(self, status, content):
        self.status_code = status
        self.content = content


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, content=None, headers=None):
        self.calls.append((url, content, headers))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class QueryBuildTests(unittest.TestCase):
    def test_build_and_parse_roundtrip(self):
        pkt = doh.build_query("example.com", 1, qid=0x1234)
        name, qtype, qid = doh.parse_question(pkt)
        self.assertEqual("example.com", name)
        self.assertEqual(1, qtype)
        self.assertEqual(0x1234, qid)

    def test_broken_packet_is_rejected(self):
        self.assertEqual(("", 0, 0), doh.parse_question(b"\x00\x01"))


class ResolveTests(unittest.TestCase):
    def test_doh_answer_is_passed_through(self):
        query = doh.build_query("example.com")
        client = _FakeClient(_FakeResponse(200, b"answer-bytes"))
        resolver = doh.DohResolver(client=client)
        self.assertEqual(b"answer-bytes", resolver.resolve(query))
        self.assertEqual(doh.DOH_URL, client.calls[0][0])
        self.assertEqual("application/dns-message", client.calls[0][2]["content-type"])

    def test_http_error_falls_back_to_servfail(self):
        query = doh.build_query("example.com")
        client = _FakeClient(_FakeResponse(500, b""))
        resolver = doh.DohResolver(client=client)
        answer = resolver.resolve(query)
        self.assertEqual(query[:2], answer[:2])          # тот же id
        self.assertEqual(0x02, answer[3] & 0x0F)         # SERVFAIL

    def test_exception_falls_back_to_servfail(self):
        query = doh.build_query("example.com")
        resolver = doh.DohResolver(client=_FakeClient(OSError("offline")))
        answer = resolver.resolve(query)
        self.assertEqual(0x02, answer[3] & 0x0F)

    def test_explicit_udp_upstream_is_used_on_failure(self):
        resolver = doh.DohResolver(client=_FakeClient(_FakeResponse(500, b"")),
                                   upstream="127.0.0.1:9", timeout=0.2)
        answer = resolver.resolve(doh.build_query("example.com"))
        self.assertEqual(0x02, answer[3] & 0x0F)


if __name__ == "__main__":
    unittest.main()
