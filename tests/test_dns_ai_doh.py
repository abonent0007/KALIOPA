"""DNS-AI: «включён» = адрес резолвера и DoH-шаблон, а не только адрес в адаптере.

Адреса DNS-AI в системе без DoH-шаблона — это открытый UDP/53, на котором сервис
не отвечает; такая машина им не обслуживается, и разблокировку должна ставить
Nova. Проверка перенесена из upstream 1.44.1.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_dns_ai as dns_ai  # noqa: E402

SERVERS = ("194.87.196.13", "45.151.102.219")
TEMPLATE = "https://dns.dns-ai.ru/dns-query"


class DohDetectionTests(unittest.TestCase):
    def test_matching_address_and_template_is_encrypted(self):
        lines = [f"194.87.196.13\t{TEMPLATE}"]
        self.assertTrue(dns_ai.doh_encrypted(SERVERS, lines=lines))

    def test_other_template_is_not_encrypted(self):
        lines = [f"194.87.196.13\thttps://example.com/dns-query"]
        self.assertFalse(dns_ai.doh_encrypted(SERVERS, lines=lines))

    def test_other_address_is_not_encrypted(self):
        lines = [f"8.8.8.8\t{TEMPLATE}"]
        self.assertFalse(dns_ai.doh_encrypted(SERVERS, lines=lines))

    def test_empty_answer_is_not_encrypted(self):
        self.assertFalse(dns_ai.doh_encrypted(SERVERS, lines=[]))


class DetectModeTests(unittest.TestCase):
    def test_native_requires_doh(self):
        native = dns_ai.detect_mode(SERVERS, servers=["194.87.196.13"], doh=lambda: True)
        self.assertEqual(dns_ai.MODE_NATIVE, native)

    def test_addresses_without_doh_are_not_native(self):
        mode = dns_ai.detect_mode(SERVERS, servers=["194.87.196.13"], doh=lambda: False)
        self.assertEqual("", mode)

    def test_foreign_resolver_is_not_dns_ai(self):
        mode = dns_ai.detect_mode(SERVERS, servers=["10.107.208.175"], doh=lambda: False)
        self.assertEqual("", mode)


if __name__ == "__main__":
    unittest.main()
