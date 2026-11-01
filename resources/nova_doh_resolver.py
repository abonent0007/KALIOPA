"""Локальный DoH-резолвер: 127.0.0.1:53 → DoH (по схеме DNS-AI).

Зачем: на Windows 10 без встроенного DoH-клиента системный DNS остаётся
открытым UDP/53, и провайдер видит запросы. DNS-AI решает это локальным
резолвером и подменой адресов в адаптерах; здесь — та же схема, но на Python
и без службы.

Модуль сознательно не трогает адаптеры сам: снимок/восстановление — отдельный
шаг (см. docs/agents/doh-resolver.md), потому что они требуют прав
администратора. Резолвер можно поднять и проверить отдельно.
"""

import socket
import struct
import threading

import httpx

DOH_URL = "https://dns.dns-ai.ru/dns-query"
DEFAULT_PORT = 53


def build_query(name, qtype=1, qid=0):
    """DNS wire-запрос (RFC 1035) для A/AAAA и любого qtype."""
    pkt = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    for part in str(name).strip(".").split("."):
        pkt += bytes([len(part)]) + part.encode("idna")
    return pkt + b"\x00" + struct.pack("!HH", int(qtype), 1)


def parse_question(data):
    """(name, qtype, qid) из запроса; ("", 0, 0) если пакет битый."""
    try:
        qid, flags, qd = struct.unpack("!HHH", data[:6])
        if qd < 1:
            return "", 0, qid
        off = 12
        labels = []
        while True:
            length = data[off]
            if length == 0:
                off += 1
                break
            if length & 0xC0:
                return "", 0, qid
            off += 1
            labels.append(data[off:off + length].decode("ascii", "replace"))
            off += length
        qtype = struct.unpack("!H", data[off:off + 2])[0]
        return ".".join(labels), qtype, qid
    except (IndexError, struct.error, UnicodeDecodeError):
        return "", 0, 0


def servfail(query):
    """Ответ SERVFAIL с тем же id/вопросом — клиент не должен ждать таймаут."""
    if len(query) < 12:
        return b""
    header = bytearray(query[:12])
    header[2] |= 0x80          # QR
    header[3] = (header[3] & 0xF0) | 0x02  # SERVFAIL
    return bytes(header) + query[12:]


class DohResolver:
    """UDP-сервер на 127.0.0.1:53, форвардящий DNS в DoH по HTTP/2."""

    def __init__(self, url=DOH_URL, host="127.0.0.1", port=DEFAULT_PORT,
                 upstream="system", timeout=4.0, client=None):
        self.url = url
        self.host = host
        self.port = int(port)
        self.upstream = upstream
        self.timeout = float(timeout)
        self._client = client
        self._sock = None
        self._thread = None
        self._stop = threading.Event()

    # -- транспорт ---------------------------------------------------------
    def _http(self):
        if self._client is None:
            self._client = httpx.Client(http2=True, timeout=self.timeout)
        return self._client

    def resolve(self, query):
        """Ответ на сырой DNS-запрос: DoH, при сбое — системный резолвер."""
        try:
            resp = self._http().post(self.url, content=query,
                                     headers={"content-type": "application/dns-message",
                                              "accept": "application/dns-message"})
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception:
            pass
        response = self._system(query)
        return response if response else servfail(query)

    def _system(self, query):
        if not self.upstream or self.upstream == "system":
            return None  # system resolver недоступен напрямую через сокет-клиент
        host, _, port = str(self.upstream).partition(":")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(self.timeout)
                s.sendto(query, (host, int(port or 53)))
                data, _ = s.recvfrom(4096)
                return data
        except OSError:
            return None

    # -- сервер ------------------------------------------------------------
    def _serve(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                query, addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(query) < 12:
                continue
            threading.Thread(target=self._answer, args=(query, addr), daemon=True,
                             name="DohResolverQuery").start()

    def _answer(self, query, addr):
        try:
            self._sock.sendto(self.resolve(query), addr)
        except OSError:
            pass

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, daemon=True, name="DohResolver")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._sock = None
        self._thread = None
