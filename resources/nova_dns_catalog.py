"""Каталог DNS-резолверов и выбор резолвера по доменным группам PAC.

Владелец видит в «Профилях → DNS» список резолверов, проверяет каждый реальным
DNS-запросом (задержка и «отвечает/нет») и назначает резолвер маршруту — ru, eu,
ai_apps, youtube, telegram, whatsapp, discord, exclude, browser. Назначение
хранится в `temp/dns-routes.json` и используется построителем NRPT-правил в
`nova.pyw`: у каждой группы имён свой резолвер, а незаданные группы идут через
общий каскад dns-ai → comss → geohide.

Проверка — существующий `nova_dns_probe.query` (UDP A-запрос), без нового кода
протокола. Адреса антиблок-резолверов — публичные данные проекта
nellimonix/warp-config-generator-vercel (MIT) и собственные замеры Nova.
"""

from __future__ import annotations

__all__ = [
    "FILENAME",
    "TEMP_DIRNAME",
    "ROUTE_ORDER",
    "ROUTE_TITLES",
    "DEFAULT_RESOLVER",
    "RESOLVERS",
    "normalize_resolver",
    "resolvers",
    "by_id",
    "addresses_of",
    "check",
    "check_many",
    "load_routes",
    "save_routes",
    "normalize_routes",
]

import json
import os
import socket
import time

FILENAME = "dns-routes.json"
TEMP_DIRNAME = "temp"

DEFAULT_RESOLVER = "cf"

# Маршрут = доменная группа PAC. Порядок — как в PAC: от частного к общему.
ROUTE_ORDER = (
    ("ru", "RU (заблокированное)"),
    ("eu", "EU / зарубежное"),
    ("ai_apps", "ИИ-приложения"),
    ("youtube", "YouTube"),
    ("telegram", "Telegram"),
    ("whatsapp", "WhatsApp"),
    ("discord", "Discord"),
    ("exclude", "Исключения (DIRECT)"),
    ("browser", "Браузеры / остальной мир"),
)
ROUTE_TITLES = dict(ROUTE_ORDER)

# Каталог: публичные DNS + антиблок-сервисы. `community=True` — резолвер отдаёт
# адреса «для обхода», поэтому его нельзя ставить на группы с прямым выходом.
RESOLVERS = (
    {"id": "cf", "title": "Cloudflare", "host": "1.1.1.1",
     "ips": ["1.1.1.1", "1.0.0.1"], "community": False, "note": "1.1.1.1"},
    {"id": "google", "title": "Google", "host": "8.8.8.8",
     "ips": ["8.8.8.8", "8.8.4.4"], "community": False, "note": "8.8.8.8"},
    {"id": "quad9", "title": "Quad9", "host": "dns.quad9.net",
     "ips": ["9.9.9.9", "149.112.112.112"], "community": False,
     "note": "Блокировка фишинга"},
    {"id": "dnsai", "title": "dns-ai.ru", "host": "dns.dns-ai.ru",
     "ips": ["194.87.196.13", "45.151.102.219"], "community": True,
     "note": "Антиблок, DoH"},
    {"id": "malw", "title": "dns.malw.link", "host": "dns.malw.link",
     "ips": ["95.216.204.218", "80.253.249.40"], "community": True, "note": "Антиблок"},
    {"id": "bezmezhau", "title": "bezmezhau.com", "host": "bezmezhau.com",
     "ips": [], "community": True, "note": "Антиблок"},
    {"id": "geohide", "title": "geohide.ru", "host": "geohide.ru",
     "ips": ["45.155.204.190", "37.230.192.51"], "community": True,
     "note": "Антиблок, GeoHide"},
    {"id": "geodema", "title": "dns.geodema.love", "host": "dns.geodema.love",
     "ips": [], "community": True, "note": "Антиблок"},
    {"id": "mafioznik", "title": "dns.mafioznik.xyz", "host": "dns.mafioznik.xyz",
     "ips": ["103.27.157.38", "103.27.157.100"], "community": True, "note": "Антиблок"},
    {"id": "comss", "title": "dns.comss.one", "host": "dns.comss.one",
     "ips": ["83.220.169.155", "212.109.195.93"], "community": True, "note": "Антиблок"},
)


def normalize_resolver(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rid = str(raw.get("id") or "").strip().lower()
    if not rid:
        return None
    host = str(raw.get("host") or "").strip().rstrip(".")
    if not host:
        return None
    ips = []
    for value in raw.get("ips") or ():
        text = str(value or "").strip()
        if text and text not in ips:
            ips.append(text)
    return {
        "id": rid,
        "title": str(raw.get("title") or "").strip()[:60] or rid,
        "host": host[:255],
        "ips": ips[:8],
        "community": bool(raw.get("community")),
        "note": str(raw.get("note") or "").strip()[:80],
    }


def resolvers(extra_geohide=()) -> list[dict]:
    """Каталог; GeoHide получает свежие адреса из nova_dns_endpoints, если они есть."""
    rows = []
    fresh = [str(item).strip() for item in (extra_geohide or ()) if str(item).strip()]
    for raw in RESOLVERS:
        row = normalize_resolver(raw)
        if row is None:
            continue
        if row["id"] == "geohide" and fresh:
            row["ips"] = fresh[:8]
        rows.append(row)
    return rows


def by_id(rows, resolver_id):
    wanted = str(resolver_id or "").strip().lower()
    for row in rows or ():
        if str(row.get("id") or "").lower() == wanted:
            return row
    return None


def addresses_of(row) -> list[str]:
    """Известные адреса резолвера; для доменного — разрешённые сейчас."""
    ips = [str(item).strip() for item in (row or {}).get("ips") or () if str(item).strip()]
    if ips:
        return ips
    host = str((row or {}).get("host") or "").strip()
    if not host:
        return []
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    out = []
    for info in infos:
        value = str(info[4][0]).strip()
        if value and value not in out:
            out.append(value)
    return out


def _query(server, timeout, query_fn):
    if query_fn is not None:
        return bool(query_fn(server, timeout))
    import nova_dns_probe
    return nova_dns_probe.query(server, "example.com", 1, timeout=timeout) is not None


def check(row, timeout: float = 2.0, query_fn=None) -> dict:
    """Проверка резолвера реальным A-запросом: ok, задержка, адреса, ошибка."""
    addresses = addresses_of(row)
    if not addresses:
        return {"id": (row or {}).get("id", ""), "ok": False, "latency_ms": None,
                "ips": [], "error": "не удалось разрешить адрес"}
    best = None
    errors = []
    for server in addresses:
        started = time.perf_counter()
        alive = _query(server, timeout, query_fn)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if alive and (best is None or elapsed_ms < best):
            best = elapsed_ms
        elif not alive:
            errors.append(f"нет ответа от {server}")
    if best is not None:
        return {"id": (row or {}).get("id", ""), "ok": True, "latency_ms": best,
                "ips": addresses, "error": ""}
    return {"id": (row or {}).get("id", ""), "ok": False, "latency_ms": None,
            "ips": addresses, "error": "; ".join(errors)[:120] or "нет ответа"}


def check_many(rows, timeout: float = 2.0, query_fn=None) -> dict:
    """Проверить весь каталог: id → результат `check`."""
    out = {}
    for row in rows or ():
        out[str(row.get("id") or "")] = check(row, timeout=timeout, query_fn=query_fn)
    return out


def normalize_routes(raw) -> dict:
    """`{"default": id, "routes": {route: id|"}}`; неизвестные маршруты и id отбрасываются."""
    data = raw if isinstance(raw, dict) else {}
    default = str(data.get("default") or DEFAULT_RESOLVER).strip().lower()
    routes = {}
    for route, _title in ROUTE_ORDER:
        value = str((data.get("routes") or {}).get(route) or "").strip().lower()
        routes[route] = value
    return {"version": 1, "default": default, "routes": routes}


def load_routes(base_dir) -> dict:
    try:
        with open(os.path.join(str(base_dir), TEMP_DIRNAME, FILENAME), "r",
                  encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return normalize_routes({})
    return normalize_routes(payload)


def save_routes(base_dir, raw) -> dict:
    data = normalize_routes(raw)
    path = os.path.join(str(base_dir), TEMP_DIRNAME, FILENAME)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        return data
    return data
