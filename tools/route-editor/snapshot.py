"""Снимок текущей конфигурации KALIOPA для Route Lab.

Читает установленную программу (не репозиторий): выбор профиля, настройки
маршрутизации, живой PAC, фактические выходные страны слотов 1370/1371 — и
обновляет `templates/kaliopa-clean.json` (шаблон, который Route Lab открывает
по умолчанию), копию в `routes/` и `resources/nova_route_spec.json` (схема,
с которой Nova сверяет настройки и PAC).

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
RESOURCE_SPEC = ROOT / "resources" / "nova_route_spec.json"
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


def live_opera_endpoint():
    cache = read_json(NOVA / "temp" / "opera_endpoint_cache.json", {})
    endpoint = str(cache.get("endpoint") or "").strip()
    return endpoint or "77.111.246.x:443"


def primary_endpoint():
    # Текущий AWG endpoint из активного Custom-профиля; fallback — измеренный 2026-11-08.
    selection = read_json(NOVA / "temp" / "profile-selection.json", {})
    profile = str(selection.get("profile") or "")
    name = profile.split("/")[-1].strip()
    if name:
        for base in (NOVA / "profiles" / ".runtime" / f"{name}.conf",
                     NOVA / "profiles" / "Custom" / f"{name}.conf"):
            try:
                text = base.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = re.search(r"Endpoint\s*=\s*(\S+)", text)
            if match:
                return match.group(1)
    return "188.114.96.248:2408"


def update_nodes(data, facts):
    nodes = {node["id"]: node for node in data.get("nodes", [])}
    endpoint = facts.get("warp_endpoint") or "188.114.96.248:2408"
    opera_endpoint = facts.get("opera_endpoint") or "77.111.244.47:443"
    if "warp" in nodes:
        nodes["warp"].update({
            "label": f"WARP · {facts['primary']}",
            "sub": f"SOCKS5 127.0.0.1:1370 · AWG UDP · выход {facts['warp_exit'] or '?'}",
        })
    if "opera" in nodes:
        nodes["opera"].update({
            "label": "Opera EU · через WARP",
            "sub": f"HTTP 127.0.0.1:1371 · выход {facts['opera_exit'] or 'NL'}",
        })
    if "opera_edge" in nodes:
        nodes["opera_edge"].update({
            "label": "Opera VPN edge (EU)",
            "sub": f"{opera_endpoint} · NL (AMS) · через WARP-диал",
            "host": opera_endpoint.split(":")[0],
            "port": opera_endpoint.split(":")[-1] if ":" in opera_endpoint else "443",
        })
    if "dns" in nodes:
        nodes["dns"].update({
            "label": "DNS-AI · DoH + NRPT",
            "sub": "127.0.0.1:53 → dns.dns-ai.ru",
            "host": "127.0.0.1",
            "port": "53",
        })
    if "dns_res" in nodes:
        nodes["dns_res"].update({
            "label": "dns-ai.ru (DoH)",
            "sub": "HTTP/2 · через SOCKS 1370",
        })
    if "cf" in nodes:
        nodes["cf"].update({"label": "WARP AWG edge", "sub": f"AWG · UDP {endpoint}"})
    if "app_web" in nodes:
        nodes["app_web"].update({"sub": "Chrome/Edge · системный PAC 1369"})

    for edge in data.get("edges", []):
        if edge.get("id") == "e-pac-warp":
            edge["condition"] = "ru/user_ru/foreign-default → 1370 · гео, не health"
            edge["label"] = "→ SOCKS5 127.0.0.1:1370"
        elif edge.get("id") == "e-pac-opera":
            edge["condition"] = (
                "ai_apps/eu/ai_second/youtube → 1371 (EU NL); "
                "Google AI/opencode/crbug → 1370 только если 1371 лёг"
            )
            edge["label"] = f"→ {facts['ai_route']}" if facts.get("ai_route") else "→ PROXY 127.0.0.1:1371"
        elif edge.get("id") == "e-pac-direct":
            edge["condition"] = "localhost·LAN·exclude·.ru·user_direct"
        elif edge.get("id") == "e-warp-cf":
            edge["transport"] = f"AWG · UDP {facts.get('warp_endpoint') or '188.114.96.248:2408'}"
        elif edge.get("id") == "e-dns-res":
            edge["transport"] = "DoH · HTTP/2"

    settings = facts.get("settings") or {}
    routes = settings.get("routes") or {}
    data["name"] = "kaliopa-clean"
    data["notes"] = (
        f"Логически верная схема KALIOPA {facts['version']} на {facts['date']}. "
        f"PAC 1369: localhost/LAN/exclude/.ru/user_direct → DIRECT; "
        f"ai_apps/eu/youtube → Opera EU 1371 (NL {opera_endpoint.split(':')[0]}); Google AI/opencode/crbug → 1371, 1370 — только если 1371 лёг. "
        f"выход Opera {facts['opera_exit'] or 'NL'}. "
        f"ru/foreign-default → WARP 1370 (выход {facts['warp_exit'] or '?'}). "
        f"Основной слот: {facts['primary']} — один слушатель Custom AWG UDP {facts.get('warp_endpoint') or '188.114.96.248:2408'}, "
        f"альтернативы на 1370 взаимоисключают его. "
        f"Opera EU диалится через WARP 1370 (bootstrap -proxy socks5h), {opera_endpoint} — NL (AMS). "
        f"Fallback 1370→1371 — гео, не health: при падении WARP нужен Tor/VLESS или рестарт WARP. "
        f"PAC — только TCP; QUIC UDP/443 — WinDivert/WFP; WinINET Ex вырезает SOCKS5. "
        f"Telegram: явный 1372 → тот же 1370 → DC. DNS-AI: NRPT 127.0.0.1:53 → DoH HTTP/2 через 1370. "
        f"Tor 1375/VLESS 1379 — холодные резервы только при secondary=tor/profile. "
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
        "warp_endpoint": primary_endpoint(),
        "opera_endpoint": live_opera_endpoint(),
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
    # Копия для программы: Nova сверяет с ней настройки и структуру PAC.
    for target in (ROUTES_COPY, RESOURCE_SPEC):
        try:
            target.write_text(payload, encoding="utf-8", newline="\n")
        except OSError:
            pass
    print(f"snapshot: {facts['version']} · основной {facts['primary']} "
          f"(выход {facts['warp_exit'] or '?'}) · Opera {facts['opera_exit'] or '?'} "
          f"· ai_apps → {facts['ai_route'] or '1371'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
