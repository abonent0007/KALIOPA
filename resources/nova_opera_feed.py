"""Published Opera endpoint list (opera_endpoints.json), read the way Nova Android reads it.

Why it exists: SurfEasy `discover` answers differently by the caller's address, and the set
handed out to Russian clients often dies on dial (opera.log: `dial tcp ...: operation was
canceled`). A list discovered from outside Russia is published next to the update manifest;
an endpoint from it is tried before the live discover, the same as a cached one.

Pure parsing lives here so tests can import it; the fetch is the only network part.
"""

import json
import os
import socket
import ssl
import struct
import urllib.error
import urllib.request

FEED_URLS = (
    "https://raw.githubusercontent.com/confeden/nova_updates/main/opera_endpoints.json",
    "https://confeden.github.io/nova_updates/opera_endpoints.json",
)
# Same regions opera-proxy takes via -country; US is the same exit as AM.
KNOWN_REGIONS = ("EU", "AM", "AS")
_ALIASES = {"US": "AM"}


def feed_urls():
    """Mirrors plus an optional `NOVA_OPERA_ENDPOINTS_URL` (comma-separated)."""
    extra = [url.strip() for url in str(os.environ.get("NOVA_OPERA_ENDPOINTS_URL", "") or "").split(",")
             if url.strip()]
    return tuple(extra) + FEED_URLS


def parse_endpoint_feed(body):
    """Return {region: [host:port, ...]} for the regions opera-proxy understands; {} on junk."""
    try:
        root = json.loads(body) if isinstance(body, str) else {}
    except (ValueError, TypeError):
        return {}
    regions = root.get("regions") if isinstance(root, dict) else None
    if not isinstance(regions, dict):
        return {}
    parsed = {}
    for raw_region, raw_endpoints in regions.items():
        region = str(raw_region or "").strip().upper()
        region = _ALIASES.get(region, region)
        if region not in KNOWN_REGIONS or not isinstance(raw_endpoints, list):
            continue
        endpoints = []
        for item in raw_endpoints:
            endpoint = str(item or "").strip()
            if ":" in endpoint and endpoint not in endpoints:
                endpoints.append(endpoint)
        if endpoints:
            parsed[region] = endpoints
    return parsed


def endpoints_for_country(feed, country):
    """Published endpoints for one region, in the feed's own order."""
    region = str(country or "").strip().upper()
    region = _ALIASES.get(region, region)
    return list((feed or {}).get(region, []))


def fetch_endpoint_feed(timeout=2.5):
    """Try every mirror; direct first, then through the live slots."""
    for url in feed_urls():
        body = _fetch_once(url, "", timeout)
        if body:
            parsed = parse_endpoint_feed(body.decode("utf-8", "replace"))
            if parsed:
                return parsed
        for proxy in slot_proxies():
            body = _fetch_once(url, proxy, max(float(timeout), 6.0))
            if body:
                parsed = parse_endpoint_feed(body.decode("utf-8", "replace"))
                if parsed:
                    return parsed
    return {}


SLOT_PORTS = ((1370, "socks5"), (1371, "http"))


def _port_open(port, timeout=0.3):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def slot_proxies(port_open=None):
    """Live Nova slots that can carry the feed: WARP SOCKS 1370, then Opera HTTP 1371.

    Direct GitHub is blocked by the DPI in Russia, while the feed is exactly the
    list "discovered from outside Russia". Without this the fetch always returned
    {} and the manager fell back to the EU pool, whose edges are dead here.
    """
    probe = port_open or _port_open
    found = []
    for port, scheme in SLOT_PORTS:
        try:
            if probe(port):
                found.append(f"{scheme}://127.0.0.1:{port}")
        except Exception:
            continue
    return found


def _read_http_body(raw: bytes) -> bytes:
    head, _, body = raw.partition(b"\r\n\r\n")
    if "transfer-encoding: chunked" in head.decode("latin-1").lower():
        out = bytearray()
        rest = body
        while True:
            line_end = rest.find(b"\r\n")
            if line_end < 0:
                break
            try:
                size = int(rest[:line_end].split(b";")[0], 16)
            except ValueError:
                break
            rest = rest[line_end + 2:]
            if size == 0:
                break
            out += rest[:size]
            rest = rest[size + 2:]
        return bytes(out)
    return body


def _socks_get(host, port, path, proxy_port, timeout):
    """Minimal SOCKS5 + TLS GET; no third-party client in the frozen build."""
    sock = None
    try:
        sock = socket.create_connection(("127.0.0.1", int(proxy_port)), timeout=timeout)
        sock.settimeout(timeout)
        sock.sendall(b"\x05\x01\x00")
        if sock.recv(2) != b"\x05\x00":
            return b""
        name = host.encode()
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack("!H", port))
        reply = sock.recv(4)
        if len(reply) < 4 or reply[1] != 0:
            return b""
        atyp = reply[3]
        if atyp == 1:
            sock.recv(4)
        elif atyp == 3:
            length = sock.recv(1)
            if length:
                sock.recv(length[0])
        elif atyp == 4:
            sock.recv(16)
        sock.recv(2)
        context = ssl.create_default_context()
        tls = context.wrap_socket(sock, server_hostname=host)
        request = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: NovaPC\r\n"
                   "Connection: close\r\n\r\n").encode()
        tls.sendall(request)
        chunks = []
        while True:
            part = tls.recv(65536)
            if not part:
                break
            chunks.append(part)
        tls.close()
        return _read_http_body(b"".join(chunks))
    except (OSError, ValueError):
        return b""
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _fetch_once(url, proxy, timeout):
    """Body of one URL via one route; b"" on any failure."""
    try:
        if not proxy:
            request = urllib.request.Request(url, headers={"User-Agent": "NovaPC"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(256 * 1024)
        scheme, _, rest = proxy.partition("://")
        if scheme == "socks5":
            proxy_port = int(rest.rsplit(":", 1)[1])
            host_path = url.split("://", 1)[1]
            host, _, tail = host_path.partition("/")
            return _socks_get(host, 443, "/" + tail, proxy_port, timeout)
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        request = urllib.request.Request(url, headers={"User-Agent": "NovaPC"})
        with opener.open(request, timeout=timeout) as response:
            return response.read(256 * 1024)
    except (urllib.error.URLError, OSError, ValueError):
        return b""
