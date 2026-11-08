"""Снимок текущей конфигурации KALIOPA для Route Lab.

Читает установленную программу (не репозиторий): выбор профиля, настройки
маршрутизации, живой PAC, фактические выходные страны слотов 1370/1371 — и
обновляет `templates/kaliopa-clean.json` (шаблон, который Route Lab открывает
по умолчанию) плюс копию в `routes/`.

Запуск: `python tools/route-editor/snapshot.py`.
Сеть нужна только для определения exit-стран; без неё подписи остаются
прежними, а остальное обновляется.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "tools" / "route-editor" / "templates" / "kaliopa-clean.json"
ROUTES_COPY = ROOT / "tools" / "route-editor" / "routes" / "kaliopa-clean.json"
NOVA = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Nova"


def read_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def version():
    text = (ROOT / "resources" / "nova_metadata.py").read_text(encoding="utf-8")
    match = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "?"


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.3):
            return True
    except OSError:
        return False


def exit_country(port, proxy_scheme):
    if not port_open(port):
        return ""
    if proxy_scheme == "socks5":
        args = ["--socks5-hostname", f"127.0.0.1:{port}"]
    else:
        args = ["--proxy", f"http://127.0.0.1:{port}"]
    try:
        result = subprocess.run(
            ["curl.exe", "-s", "--max-time", "12", *args,
             "https://www.cloudflare.com/cdn-cgi/trace"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in (result.stdout or "").splitlines():
        if line.startswith("loc="):
            return line.split("=", 1)[1].strip()
    return ""


def ai_route():
    try:
        pac = (NOVA / "temp" / "nova.pac").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = re.search(r'matchDomain\(ai_apps, host\)\) return "(PROXY|SOCKS5) ([^"]+)"', pac)
    return f"{match.group(1)} {match.group(2)}" if match else ""


def primary_name():
    selection = read_json(NOVA / "temp" / "profile-selection.json", {})
    if selection.get("mode") == "profile" and selection.get("profile"):
        return str(selection["profile"])
    state = read_json(NOVA / "temp" / "awg-profile-state.json", {})
    if state.get("preferred_profile"):
        return str(state["preferred_profile"])
    group = selection.get("group")
    return f"группа {group}" if group else "авто"


def update_nodes(data, facts):
    nodes = {node["id"]: node for node in data.get("nodes", [])}
    if "warp" in nodes:
        nodes["warp"].update({
            "label": f"WARP · {facts['primary']}",
            "sub": f"SOCKS5 127.0.0.1:1370 · выход {facts['warp_exit'] or '?'}",
        })
    if "opera" in nodes:
        nodes["opera"].update({
            "label": "Opera US · через WARP",
            "sub": f"HTTP 127.0.0.1:1371 · выход {facts['opera_exit'] or '?'}",
        })
    if "opera_edge" in nodes:
        nodes["opera_edge"].update({
            "label": "Opera VPN edge (US)",
            "sub": "77.111.246.x:443 · через WARP-диал",
        })
    if "dns" in nodes:
        nodes["dns"].update({
            "label": "DNS-AI · DoH + NRPT",
            "sub": "127.0.0.1:53 → dns.dns-ai.ru",
        })
    if "dns_res" in nodes:
        nodes["dns_res"].update({
            "label": "dns-ai.ru (DoH)",
            "sub": "HTTP/2 · US-прокси",
        })
    if "cf" in nodes:
        nodes["cf"].update({"sub": "WARP / MASQUE · 162.159.x"})
    if "app_web" in nodes:
        nodes["app_web"].update({"sub": "Chrome/Edge · системный PAC"})

    for edge in data.get("edges", []):
        if edge.get("id") == "e-pac-warp":
            edge["condition"] = "browser · RU · auto"
        elif edge.get("id") == "e-pac-opera":
            edge["condition"] = "ai_apps · US"
            edge["label"] = f"→ {facts['ai_route']}" if facts.get("ai_route") else "HTTP CONNECT 1371"
        elif edge.get("id") == "e-pac-direct":
            edge["condition"] = ".ru · exclude · last_resort"
        elif edge.get("id") == "e-warp-cf":
            edge["transport"] = "AWG · UDP"

    settings = facts.get("settings") or {}
    routes = settings.get("routes") or {}
    data["name"] = "kaliopa-clean"
    data["notes"] = (
        f"Снимок установленной KALIOPA {facts['version']} на {facts['date']}. "
        f"Основной слот: {facts['primary']} (1370, выход {facts['warp_exit'] or '?'}); "
        f"Opera US (1371, выход {facts['opera_exit'] or '?'}) идёт через WARP-диал; "
        f"PAC: ai_apps → {facts['ai_route'] or '1371'}, браузер/Telegram → 1370; "
        f"DNS-AI: DoH 127.0.0.1:53 → dns.dns-ai.ru. "
        f"Маршруты: " + ", ".join(f"{k}={v}" for k, v in sorted(routes.items())) + "."
    )
    return data


def main() -> int:
    import datetime

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    settings = read_json(NOVA / "routing_settings.json", {})
    facts = {
        "version": version(),
        "date": datetime.date.today().isoformat(),
        "primary": primary_name(),
        "warp_exit": exit_country(1370, "socks5"),
        "opera_exit": exit_country(1371, "http"),
        "ai_route": ai_route(),
        "settings": settings,
    }
    data = read_json(TEMPLATE, None)
    if not isinstance(data, dict):
        print("snapshot: шаблон не найден:", TEMPLATE)
        return 1
    data = update_nodes(data, facts)
    payload = json.dumps(data, ensure_ascii=False, indent=4) + "\n"
    TEMPLATE.write_text(payload, encoding="utf-8", newline="\n")
    try:
        ROUTES_COPY.write_text(payload, encoding="utf-8", newline="\n")
    except OSError:
        pass
    print(f"snapshot: {facts['version']} · основной {facts['primary']} "
          f"(выход {facts['warp_exit'] or '?'}) · Opera {facts['opera_exit'] or '?'} "
          f"· ai_apps → {facts['ai_route'] or '1371'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
