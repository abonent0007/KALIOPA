"""DoH-транспорт для DNS-AI: локальный резолвер поверх `nova-go dns doh`.

Зачем отдельный модуль. У dns-ai.ru нет обычного UDP/53: сервис отвечает только
по DoH (`https://dns.dns-ai.ru/dns-query`) и требует HTTP/2 — на HTTP/1.1
отдаёт 505. NRPT-правила Windows умеют указывать только IP-адрес сервера, а
встроенного DoH-клиента на этой сборке Windows нет (`Get-DnsClientDohServerAddress`
отсутствует). Поэтому Nova поднимает свой резолвер: слушает 127.0.0.1:53 и
пересылает каждый запрос в DoH через `nova-go dns doh` (Go сам берёт HTTP/2).

Прямой доступ к endpoint в РФ рвётся DPI, поэтому апстрим идёт через живой слот
Nova: сначала WARP SOCKS 127.0.0.1:1370, затем HTTP Opera 127.0.0.1:1371.
Без туннеля DoH не работает — тогда правил нет и индикатор остаётся серым.

Кэш поддержки (`temp\dns_doh_support.json`) отдельный от UDP-каскада: подпись
включает имена и апстрим, поэтому смена списка имён сама сбрасывает кэш.
"""

from __future__ import annotations

__all__ = [
    "LISTEN_HOST",
    "LISTEN_PORT",
    "UPSTREAM",
    "CACHE_FILENAME",
    "proxy_url",
    "start",
    "stop",
    "running",
    "query",
    "supported_names",
    "load_cache",
    "save_cache",
]

import json
import os
import socket
import subprocess
import tempfile
import time
from typing import Any

import nova_dns_probe

LISTEN_HOST = "127.0.0.1"
# NRPT умеет только IP без порта, поэтому «свой порт» для DNS-AI — это свой loopback-адрес.
# 127.0.0.1:53 может занимать сторонний резолвер (dns-ai.exe, AdGuard); тогда резолвер
# Nova садится на 127.0.0.2:53 и правила указывают туда.
LISTEN_HOSTS = ("127.0.0.1", "127.0.0.2")
LISTEN_PORT = 53
UPSTREAM = "https://dns.dns-ai.ru/dns-query"
CACHE_FILENAME = "dns_doh_support.json"
TEMP_DIRNAME = "temp"
CACHE_MAX_AGE_SEC = 24 * 60 * 60
START_TIMEOUT_SEC = 8.0
QUERY_TIMEOUT_SEC = 5.0
LOG_PREFIX = "[DNS-AI]"

_process = None
_listen_host = LISTEN_HOST


def listen_host() -> str:
    """Адрес, на котором фактически слушает резолвер (127.0.0.1 или 127.0.0.2)."""
    return _listen_host


def _port_open(port: int, host: str = LISTEN_HOST, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_busy(probe, host: str) -> bool:
    """`probe` may be host-aware (tests) or the plain one-argument check."""
    try:
        return bool(probe(LISTEN_PORT, host))
    except TypeError:
        return bool(probe(LISTEN_PORT))


def proxy_url(port_open=None) -> str:
    """WARP SOCKS first (the primary slot), then the Opera HTTP slot, else direct."""
    probe = port_open or _port_open
    try:
        if probe(1370):
            return "socks5://127.0.0.1:1370"
        if probe(1371):
            return "http://127.0.0.1:1371"
    except Exception:
        pass
    return ""


def running() -> bool:
    proc = _process
    return bool(proc is not None and proc.poll() is None)


def query(name: str, qtype: int = 1, timeout: float = QUERY_TIMEOUT_SEC, query_fn=None) -> list | None:
    """Resolve a name through the local stub; any transport error is «нет ответа»."""
    fn = query_fn or nova_dns_probe.query
    try:
        return fn(_listen_host, name, qtype, timeout)
    except Exception:
        return None


def _stub_answers(timeout: float = START_TIMEOUT_SEC) -> bool:
    deadline = time.time() + max(1.0, timeout)
    while time.time() < deadline:
        if running() is False and _process is not None:
            return False
        if query("example.com", 1, timeout=1.0) is not None:
            return True
        time.sleep(0.25)
    return False


def start(nova_go_path: str, log, base_dir: str = "", parent_pid: int = 0,
          port_open=None) -> tuple[bool, str]:
    """Start the helper once; returns (ok, reason). Never raises."""
    global _process, _listen_host
    if running():
        return True, ""
    if not nova_go_path or not os.path.exists(nova_go_path):
        return False, "nova-go.exe не найден"
    host = LISTEN_HOST
    probe = port_open or _port_open
    if _probe_busy(probe, LISTEN_HOST):
        # 127.0.0.1:53 занят (dns-ai.exe, AdGuard, другой резолвер) — NRPT умеет
        # только адрес без порта, поэтому «свой порт» здесь — это 127.0.0.2:53.
        host = next((candidate for candidate in LISTEN_HOSTS[1:]
                     if not _probe_busy(probe, candidate)), "")
        if not host:
            return False, "127.0.0.1:53 и 127.0.0.2:53 заняты другими резолверами"
    _listen_host = host
    proxy = proxy_url(port_open=port_open)
    args = [
        nova_go_path, "dns", "doh",
        "--listen", f"{host}:{LISTEN_PORT}",
        "--upstream", UPSTREAM,
        "--cache", "60s",
        "--timeout", f"{int(QUERY_TIMEOUT_SEC)}s",
    ]
    if proxy:
        args += ["--proxy", proxy]
    if parent_pid:
        args += ["--parent-pid", str(int(parent_pid))]
    log_path = ""
    log_handle = None
    stderr_target: Any = subprocess.DEVNULL
    try:
        if base_dir:
            temp_dir = os.path.join(base_dir, TEMP_DIRNAME)
            os.makedirs(temp_dir, exist_ok=True)
            log_path = os.path.join(temp_dir, "dns-doh.log")
            log_handle = open(log_path, "w", encoding="utf-8", errors="ignore")
            stderr_target = log_handle
        _process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=stderr_target,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
    except OSError as exc:
        if log_handle is not None:
            log_handle.close()
        _process = None
        return False, f"не удалось запустить резолвер: {type(exc).__name__}"
    finally:
        if log_handle is not None:
            log_handle.close()
    if not _stub_answers():
        reason = "резолвер не ответил за отведённое время"
        if log_path and os.path.exists(log_path):
            try:
                tail = open(log_path, "r", encoding="utf-8", errors="ignore").read().strip().splitlines()
                if tail:
                    reason += f" ({tail[-1][:120]})"
            except OSError:
                pass
        stop(log=log)
        return False, reason
    if log:
        log(f"{LOG_PREFIX} резолвер поднят: {host}:{LISTEN_PORT} через "
            f"{proxy or 'прямое соединение'}")
    return True, ""


def stop(log=None) -> None:
    global _process
    proc, _process = _process, None
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
    except OSError:
        pass
    if log:
        log(f"{LOG_PREFIX} резолвер остановлен")


def _reference_server() -> str:
    """The machine's current DNS: the first IPv4 from the adapter settings."""
    try:
        import nova_dns_ai
        for server in sorted(nova_dns_ai.system_dns_servers()):
            if ":" not in server and server.count(".") == 3:
                return server
    except Exception:
        pass
    return "77.88.8.8"


def supported_names(names, reference_fn=None, query_fn=None) -> dict[str, list[str]]:
    """Names where DoH answers differ from the machine's DNS → NRPT rule to the stub.

    A name whose DoH answer matches the system one gains nothing from a rule; a name
    the stub cannot resolve is skipped as well. The result maps name → ["127.0.0.1"].
    """
    local = query_fn or query
    reference_server = _reference_server()
    reference = reference_fn or (lambda name: nova_dns_probe.resolve(reference_server, name, 2.0))
    supported: dict[str, list[str]] = {}
    for name in names:
        try:
            doh_ips = set(local(name) or [])
        except Exception:
            continue
        if not doh_ips:
            continue
        try:
            ref_ips = set(reference(name) or [])
        except Exception:
            ref_ips = set()
        if ref_ips and not (doh_ips - ref_ips):
            continue
        supported[name] = [_listen_host]
    return supported


def _cache_path(base_dir: str) -> str:
    return os.path.join(str(base_dir), TEMP_DIRNAME, CACHE_FILENAME)


def load_cache(base_dir: str, signature: str, max_age: float = CACHE_MAX_AGE_SEC) -> dict | None:
    if not base_dir:
        return None
    try:
        with open(_cache_path(base_dir), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("sig") != signature:
        return None
    at = data.get("at")
    if not isinstance(at, (int, float)) or (time.time() - at) > max_age:
        return None
    support = data.get("support")
    return support if isinstance(support, dict) else None


def save_cache(base_dir: str, signature: str, support: dict) -> None:
    if not base_dir:
        return
    path = _cache_path(base_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="doh-support-", suffix=".tmp", dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"sig": signature, "at": int(time.time()), "support": support},
                      handle, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass
