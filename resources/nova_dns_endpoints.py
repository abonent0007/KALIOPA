"""GeoHide DNS: адреса резолвера берутся из hosts-файла сервиса, а не только из кода.

Сервис публикует список своих адресов в шапке hosts-файлов на GitHub:

    ### geohide.ru: hosts file
    # Последнее обновление: 20.10.2026 04:56:02
    # Регион серверов: RU
    # Эти IP-адреса принадлежат GeoHide DNS:
    # 159.194.200.33
    # ...

16 адресов на 2026-10-20 против двух, что были зашиты в `nova.pyw`
(`45.155.204.190`, `37.230.192.51`); первый из них сервис уже не публикует.
Поэтому список обновляется из сети, а зашитый набор остаётся аварийным
fallback-ом: без сети, с битым кэшем или при смене формата Nova работает как
раньше.

Сеть трогается только в фоновом потоке и не чаще раза в сутки; старт берёт
кэш прошлого запуска (или fallback) и ничего не ждёт.
"""

import contextlib
import ipaddress
import json
import os
import re
import threading
import time
import urllib.request

CACHE_NAME = "dns_endpoints.json"
# Обновление пробуем не чаще раза в сутки; кэш считаем годным две недели.
REFRESH_INTERVAL_S = 24 * 3600
CACHE_MAX_AGE_S = 14 * 86400
# Windows NRPT практичнее держать коротким: адреса упорядочены самим сервисом.
MAX_SERVERS = 6

SOURCES = (
    "https://raw.githubusercontent.com/Internet-Helper/GeoHideDNS/main/hosts/hosts",
    "https://raw.githubusercontent.com/Internet-Helper/GeoHideDNS/main/hosts/us/hosts",
)
MARKER = "GeoHide DNS"
UPDATE_PREFIX = "Последнее обновление"

# Пул адресов по регионам — из hostPools на самом geohide.ru (2026-10-31).
# NRPT сейчас использует RU-пул; EU/US пригодятся, если регион станет
# настраиваемым (сайт отдаёт и отдельные DoH: eu./us.geohide.ru/dns-query).
REGION_POOLS = {
    "ru": ("193.233.112.67", "193.233.112.68"),
    "eu": ("217.60.245.219", "217.60.245.233", "31.25.239.132", "143.20.64.192", "2.27.118.34"),
    "us": ("192.255.159.240", "192.255.159.241", "192.3.233.253", "107.175.76.134"),
}

# Наблюдаемый аптайм по публичному отчёту HetrixTools «GeoHide DNS» (2026-10-31):
# 37.230.192.51 99.76 %, 159.194.200.33 99.59 %, 193.233.112.68 90.59 %,
# 193.233.112.88 87.11 %, 193.233.112.67 82.10 %. Windows пробует адреса
# правила по порядку, поэтому здоровые идут первыми.
UPTIME_RANK = {
    "37.230.192.51": 99.76,
    "159.194.200.33": 99.59,
    "193.233.112.68": 90.59,
    "193.233.112.88": 87.11,
    "193.233.112.67": 82.10,
}

# Снимок блока «Эти IP-адреса принадлежат GeoHide DNS» на 2026-10-20 (RU-файл).
FALLBACK_SERVERS = (
    "159.194.200.33",
    "193.233.112.67",
    "193.233.112.68",
    "193.233.112.88",
    "37.230.192.51",
    "5.175.161.3",
    "5.175.161.40",
    "37.221.93.141",
    "37.221.93.128",
    "45.13.237.213",
    "31.25.239.132",
    "143.20.64.192",
    "192.255.159.240",
    "192.255.159.241",
    "192.3.233.253",
    "107.175.76.134",
)

_ADDRESS_LINE = re.compile(r"^#\s*([0-9a-fA-F:.]+)\s*$")
_refresh_lock = threading.Lock()
_refresh_started = False


def parse_servers(text):
    """Адреса из шапки hosts-файла; всё, что ниже блока, игнорируется."""
    lines = str(text or "").splitlines()
    for index, line in enumerate(lines):
        if MARKER not in line:
            continue
        found = []
        for candidate in lines[index + 1:]:
            match = _ADDRESS_LINE.match(candidate.strip())
            if not match:
                break
            try:
                address = ipaddress.ip_address(match.group(1))
            except ValueError:
                continue
            if address.is_global:
                found.append(str(address))
        return tuple(dict.fromkeys(found))
    return ()


def parse_update_date(text):
    """Строка «Последнее обновление» из шапки, или ""."""
    for line in str(text or "").splitlines()[:5]:
        if UPDATE_PREFIX in line and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""


def order_servers(servers):
    """Известные адреса по аптайму, незнакомые — в конце, порядок внутри сохранён."""
    seen = list(dict.fromkeys(servers))
    known = sorted((s for s in seen if s in UPTIME_RANK), key=lambda s: -UPTIME_RANK[s])
    unknown = [s for s in seen if s not in UPTIME_RANK]
    return tuple(known + unknown)


def cache_path(base_dir):
    return os.path.join(str(base_dir), "temp", CACHE_NAME)


def read_cache(base_dir):
    """(servers, updated_at). Пустой список, если кэша нет или он нечитаем."""
    try:
        with open(cache_path(base_dir), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return (), 0.0
    servers = []
    for value in data.get("servers") or ():
        try:
            address = ipaddress.ip_address(str(value).strip())
        except ValueError:
            continue
        if address.is_global:
            servers.append(str(address))
    try:
        updated_at = float(data.get("updated_at") or 0)
    except (TypeError, ValueError):
        updated_at = 0.0
    return tuple(dict.fromkeys(servers))[:MAX_SERVERS], updated_at


def servers_for_startup(base_dir):
    """Адреса для NRPT прямо сейчас: свежий кэш, иначе снимок из кода.

    Побочно запускает фоновое обновление (один раз за процесс). Старт не ждёт сеть.
    """
    cached, updated_at = read_cache(base_dir)
    if cached and time.time() - updated_at <= CACHE_MAX_AGE_S:
        servers = cached
    else:
        servers = order_servers(FALLBACK_SERVERS)[:MAX_SERVERS]
    _start_refresh(base_dir)
    return tuple(servers)


def _start_refresh(base_dir):
    global _refresh_started
    if str(os.environ.get("NOVA_DNS_ENDPOINTS_AUTO", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return
    with _refresh_lock:
        if _refresh_started:
            return
        _refresh_started = True
    thread = threading.Thread(
        target=refresh, args=(base_dir,), kwargs={"log": None}, daemon=True,
        name="NovaDnsEndpoints",
    )
    thread.start()


def _fetch(url, timeout=8.0):
    request = urllib.request.Request(url, headers={"User-Agent": "Nova/1.0 (+dns-endpoints)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(512 * 1024).decode("utf-8", "replace")


def refresh(base_dir, fetch=None, log=None):
    """Обновить кэш из источников. Возвращает {"ok", "count", "updated_at"}; не бросает."""
    servers = []
    remote_date = ""
    used_source = ""
    for url in SOURCES:
        try:
            text = _fetch(url) if fetch is None else fetch(url)
        except Exception:
            continue
        found = parse_servers(text)
        if not found:
            continue
        used_source = url
        remote_date = remote_date or parse_update_date(text)
        for value in found:
            if value not in servers:
                servers.append(value)
    if len(servers) < 4:
        if callable(log):
            with contextlib.suppress(Exception):
                log("[DNS] GeoHide: список не получен, остаётся прежний")
        return {"ok": False, "count": 0, "updated_at": 0.0}

    servers = list(order_servers(servers))[:MAX_SERVERS]
    now = time.time()
    payload = {
        "servers": servers,
        "updated_at": now,
        "source": used_source,
        "remote_date": remote_date,
    }
    try:
        path = cache_path(base_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        return {"ok": False, "count": len(servers), "updated_at": now}
    if callable(log):
        try:
            log(f"[DNS] GeoHide: адреса обновлены ({len(servers)}, {remote_date or 'без даты'})")
        except Exception:
            pass
    return {"ok": True, "count": len(servers), "updated_at": now}
