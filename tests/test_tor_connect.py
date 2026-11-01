"""Перебор адресов в `_connect_public`: сбой одного семейства не должен обрывать пробу.

Раньше `socket.socket()` стоял вне try, и OSError на первом адресе (например,
неподдержанное семейство) выбрасывал исключение, хотя второй адрес был рабочим.
Тест фиксирует: пробуем следующий target, а ошибку отдаём только когда кончились
все.
"""

import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_tor  # noqa: E402


class _FakeSocket:
    def __init__(self):
        self.connected = None
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def connect(self, addr):
        self.connected = addr

    def close(self):
        self.closed = True


class TorConnectTests(unittest.TestCase):
    def test_second_family_is_tried_after_socket_error(self):
        fake = _FakeSocket()
        created = []

        def socket_factory(family, kind):
            created.append(family)
            if len(created) == 1:
                raise OSError("family not supported")
            return fake

        targets = [(socket.AF_INET6, ("::1", 443)), (socket.AF_INET, ("1.1.1.1", 443))]
        with mock.patch.object(nova_tor, "_public_probe_targets", return_value=targets), \
                mock.patch.object(nova_tor.socket, "socket", side_effect=socket_factory):
            sock = nova_tor._connect_public("example.com", 443, 1.0)

        self.assertIs(fake, sock)
        self.assertEqual(("1.1.1.1", 443), fake.connected)
        self.assertEqual([socket.AF_INET6, socket.AF_INET], created)

    def test_all_families_failing_raises_last_error(self):
        targets = [(socket.AF_INET6, ("::1", 443))]
        with mock.patch.object(nova_tor, "_public_probe_targets", return_value=targets), \
                mock.patch.object(nova_tor.socket, "socket", side_effect=OSError("no sockets")):
            with self.assertRaises(OSError):
                nova_tor._connect_public("example.com", 443, 1.0)


if __name__ == "__main__":
    unittest.main()
