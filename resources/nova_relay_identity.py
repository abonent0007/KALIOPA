"""Динамическая личность релея: версия логина подбирается под ключ.

Релей проверяет Basic-логин `nova-pc-<version>` вместе с ключом
`profiles/opera_relay.key`, и версия в логине должна быть той, под которую ключ
выпущен. В форке стояла константа `1.43.2`, потому что ключ был из 1.43.2; у
релиза upstream ключ уже другой (проверено: upstream-ключ из 1.44.2 принимает
логин `nova-pc-1.44.1`, а `1.44.2` получает 407).

Модуль не гадает: он берёт версии из релизов upstream, пробует их по очереди
через WARP и запоминает ту, которую ключ реально принимает. Пока проба
невозможна (WARP ещё не поднят, relay недоступен), используется последняя
проверенная пара из `temp/relay_identity.json` или `profiles/opera_relay.version`.

Ключ никогда не логируется и не уходит в репозиторий: наружу отдаётся только
его SHA-256-префикс, чтобы кэш инвалидировался при замене файла.
"""

import base64
import hashlib
import json
import os
import re
import socket
import ssl
import struct
import threading
import time
import urllib.request

DEFAULT_VERSION = "1.44.1"
CACHE_FILENAME = "relay_identity.json"
VERSION_FILENAME = "opera_relay.version"
RELAY_HOST = "relay.nova-app.eu"
RELAY_PORT = 8443
UPSTREAM_VERSION_URLS = (
    "https://raw.githubusercontent.com/confeden/nova_updates/main/version.json",
    "https://confeden.github.io/nova_updates/version.json",
)
RELEASES_ATOM_URL = "https://github.com/confeden/Nova/releases.atom"
VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)*$")
ATOM_TITLE_RE = re.compile(r"<title>\s*v?(\d+\.\d+(?:\.\d+)*)\s*</title>", re.I)
PROBE_TIMEOUT = 4.0
FALLBACK_VERSIONS = ("1.44.1", "1.43.2")

_refresh_lock = threading.Lock()
_refresh_thread = None


def _valid_version(value):
    text = str(value or "").strip().lstrip("v")
    return text if VERSION_RE.match(text) else ""


def _key_paths(base_dir):
    root = str(base_dir or "")
    return [
        os.path.join(root, "profiles", "opera_relay.key"),
        os.path.join(root, "awg", "opera_relay.key"),
    ]


def read_key(base_dir):
    for path in _key_paths(base_dir):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def key_fingerprint(key):
    return hashlib.sha256(str(key or "").encode("utf-8")).hexdigest()[:16]


def _cache_path(base_dir):
    return os.path.join(str(base_dir or ""), "temp", CACHE_FILENAME)


def load_cache(base_dir):
    try:
        with open(_cache_path(base_dir), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(base_dir, data):
    path = _cache_path(base_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def _marker_path(base_dir):
    return os.path.join(str(base_dir or ""), "profiles", VERSION_FILENAME)


def read_marker(base_dir):
    try:
        with open(_marker_path(base_dir), "r", encoding="utf-8") as handle:
            return _valid_version(handle.read())
    except OSError:
        return ""


def write_marker(base_dir, version):
    path = _marker_path(base_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(str(version).strip() + "\n")
        os.replace(tmp, path)
    except OSError:
        pass


def current_version(base_dir, environ=None):
    """Версия для логина: env > кэш под тот же ключ > маркер > DEFAULT."""
    env = os.environ if environ is None else environ
    override = _valid_version(env.get("NOVA_RELAY_KEY_VERSION", ""))
    if override:
        return override
    key = read_key(base_dir)
    fingerprint = key_fingerprint(key) if key else ""
    cached = load_cache(base_dir)
    if fingerprint and str(cached.get("key_sha256") or "") == fingerprint:
        version = _valid_version(cached.get("version"))
        if version:
            return version
    marker = read_marker(base_dir)
    if marker:
        return marker
    return DEFAULT_VERSION


def _http_text(url, timeout=4.0):
    request = urllib.request.Request(str(url), headers={"User-Agent": "NovaPC"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(256 * 1024).decode("utf-8", "replace")
    except Exception as exc:
        raise OSError("не удалось прочитать %s: %s" % (url, exc)) from exc


def fetch_upstream_version(timeout=4.0, fetcher=None):
    fetch = fetcher or _http_text
    for url in UPSTREAM_VERSION_URLS:
        try:
            data = json.loads(fetch(url, timeout=timeout))
            version = _valid_version(data.get("version") if isinstance(data, dict) else "")
            if version:
                return version
        except Exception:
            continue
    return ""


def fetch_release_versions(timeout=5.0, fetcher=None):
    fetch = fetcher or _http_text
    try:
        body = fetch(RELEASES_ATOM_URL, timeout=timeout)
    except Exception:
        return []
    found = []
    for version in ATOM_TITLE_RE.findall(body or ""):
        version = _valid_version(version)
        if version and version not in found:
            found.append(version)
    return found


def candidate_versions(base_dir, upstream="", releases=None):
    key = read_key(base_dir)
    fingerprint = key_fingerprint(key) if key else ""
    cached = load_cache(base_dir)
    versions = []
    if fingerprint and str(cached.get("key_sha256") or "") == fingerprint:
        versions.append(_valid_version(cached.get("version")))
    versions.append(_valid_version(upstream))
    versions.extend(releases or ())
    marker = read_marker(base_dir)
    versions.append(marker)
    versions.extend(FALLBACK_VERSIONS)
    result = []
    for version in versions:
        if version and version not in result:
            result.append(version)
    return result


def _recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("relay closed the connection")
        data.extend(chunk)
    return bytes(data)


def _socks_connect(sock, host, port):
    sock.sendall(b"\x05\x01\x00")
    if _recv_exact(sock, 2) != b"\x05\x00":
        raise OSError("SOCKS5 auth refused")
    name = host.encode("idna")
    sock.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack("!H", int(port)))
    head = _recv_exact(sock, 4)
    if head[0] != 0x05 or head[1] != 0x00:
        raise OSError("SOCKS5 connect refused")
    atyp = head[3]
    if atyp == 0x01:
        _recv_exact(sock, 4)
    elif atyp == 0x04:
        _recv_exact(sock, 16)
    elif atyp == 0x03:
        _recv_exact(sock, _recv_exact(sock, 1)[0])
    else:
        raise OSError("SOCKS5 unknown address type")
    _recv_exact(sock, 2)


def _connect(host, port, proxy, timeout):
    if proxy:
        sock = socket.create_connection(tuple(proxy), timeout=timeout)
        try:
            _socks_connect(sock, host, port)
            return sock
        except Exception:
            sock.close()
    return socket.create_connection((host, port), timeout=timeout)


def probe_identity(version, key, timeout=PROBE_TIMEOUT, proxy=("127.0.0.1", 1370),
                   host=RELAY_HOST, port=RELAY_PORT):
    """'ok' — ключ принят, 'auth' — 407, 'unreachable' — нет пути, 'error' — прочее."""
    login = "nova-pc-%s" % _valid_version(version)
    if not _valid_version(version) or not key:
        return "error"
    try:
        sock = _connect(host, port, proxy, timeout)
    except OSError:
        return "unreachable"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            token = base64.b64encode(("%s:%s" % (login, key)).encode("utf-8")).decode("ascii")
            request = (
                "CONNECT api2.sec-tunnel.com:443 HTTP/1.1\r\n"
                "Host: api2.sec-tunnel.com:443\r\n"
                "Proxy-Authorization: Basic %s\r\n"
                "Proxy-Connection: close\r\n\r\n" % token
            )
            tls.sendall(request.encode("ascii"))
            head = tls.recv(256)
    except (OSError, ssl.SSLError):
        return "error"
    match = re.match(rb"HTTP/\d(?:\.\d)?\s+(\d{3})", head.split(b"\r\n", 1)[0] + b" ")
    if not match:
        return "error"
    code = int(match.group(1))
    if code == 407:
        return "auth"
    return "ok" if 200 <= code < 300 else "error"


def resolve(base_dir, log=None, prober=None, fetcher=None, timeout=PROBE_TIMEOUT):
    """Проверить кандидатов и сохранить версию, которую принял ключ."""
    say = log if callable(log) else (lambda _text: None)
    key = read_key(base_dir)
    if not key:
        return {"version": current_version(base_dir), "verified": False, "reason": "no-key", "upstream": ""}
    upstream = fetch_upstream_version(fetcher=fetcher)
    releases = fetch_release_versions(fetcher=fetcher)
    versions = candidate_versions(base_dir, upstream, releases)
    probe = prober or (lambda version: probe_identity(version, key, timeout=timeout))
    for version in versions:
        status = probe(version)
        if status == "ok":
            fingerprint = key_fingerprint(key)
            save_cache(base_dir, {
                "version": version,
                "upstream": upstream,
                "key_sha256": fingerprint,
                "checked_at": time.time(),
                "verified": True,
            })
            write_marker(base_dir, version)
            say("[Relay] ключ принят для версии %s (upstream: %s)." % (version, upstream or "?"))
            return {"version": version, "verified": True, "reason": "ok", "upstream": upstream}
        if status == "unreachable":
            say("[Relay] версия не проверена: пути к relay нет; остаюсь на %s."
                % current_version(base_dir))
            return {"version": current_version(base_dir), "verified": False,
                    "reason": "unreachable", "upstream": upstream}
    version = current_version(base_dir)
    say("[Relay] ни один кандидат не подошёл к ключу; остаюсь на %s." % version)
    return {"version": version, "verified": False, "reason": "no-match", "upstream": upstream}


def refresh_async(base_dir, log=None, delay=15.0, attempts=8, pause=30.0):
    """Фоновая проверка: WARP может подняться позже первого запуска."""
    global _refresh_thread
    with _refresh_lock:
        if _refresh_thread is not None and _refresh_thread.is_alive():
            return _refresh_thread
        def worker():
            if delay > 0:
                time.sleep(delay)
            for _ in range(max(1, int(attempts))):
                result = resolve(base_dir, log)
                if result.get("verified") or result.get("reason") in ("no-key", "error"):
                    return
                time.sleep(max(5.0, float(pause)))
        _refresh_thread = threading.Thread(target=worker, daemon=True, name="NovaRelayIdentity")
        _refresh_thread.start()
        return _refresh_thread
