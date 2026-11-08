"""Проверка живой политики KALIOPA против конфигурации Route Lab.

Скрипт только читает: настройки, PAC и локальные порты. Он не меняет маршруты
и не запускает туннели. Нужен, чтобы после правок и перезапуска видеть, что
браузер действительно идёт через PAC 1370/1371/DIRECT, Telegram — через WARP,
а Tor/VLESS остаются резервом.

Использование:
  python tools/route_policy_check.py
  python tools/route_policy_check.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
if str(RESOURCES) not in sys.path:
    sys.path.insert(0, str(RESOURCES))

import nova_route_spec  # noqa: E402

REQUIRED_OPEN = (1369, 1370, 1371, 1372)
RESERVE_CLOSED = (1375, 1378, 1379, 1380)
PAC_URL = "http://127.0.0.1:1369/nova.pac"


def check_settings(settings: dict) -> list[str]:
    """Устойчивая политика схемы — в ресурсе программы, не в этом скрипте."""
    return nova_route_spec.settings_issues(settings)


def check_primary(selection: dict) -> list[str]:
    issues = []
    mode = str(selection.get("mode") or "").strip().lower()
    group = str(selection.get("group") or "").strip()
    if mode not in ("auto", "group", "profile"):
        issues.append("profile-selection.mode неизвестен: %r" % mode)
    if group and group not in ("MASQUE", "AWG Proton", "AWG Cloudflare", "VLESS", "Custom"):
        issues.append("primary-группа вне списка слотов: %r" % group)
    if mode == "profile" and not str(selection.get("profile") or "").strip():
        issues.append("profile-selection: режим profile без profile id")
    return issues


def check_pac(pac: str) -> list[str]:
    issues = []
    if "SOCKS5 127.0.0.1:1370" not in pac:
        issues.append("PAC не содержит SOCKS5 1370")
    if "PROXY 127.0.0.1:1371" not in pac:
        issues.append("PAC не содержит HTTP 1371")
    if "DIRECT" not in pac:
        issues.append("PAC не содержит DIRECT")
    for port in RESERVE_CLOSED:
        if "127.0.0.1:%d" % port in pac:
            issues.append("PAC содержит резервный порт %d" % port)
    return issues


def check_ports(open_ports, closed_ports) -> list[str]:
    issues = []
    open_ports = set(int(port) for port in open_ports)
    closed_ports = set(int(port) for port in closed_ports)
    for port in REQUIRED_OPEN:
        if port not in open_ports:
            issues.append("порт %d должен быть открыт" % port)
    for port in RESERVE_CLOSED:
        if port not in closed_ports:
            issues.append("резервный порт %d должен быть закрыт" % port)
    return issues


def probe_ports(timeout=0.35):
    opened, closed = set(), set()
    for port in REQUIRED_OPEN + RESERVE_CLOSED:
        with socket.socket() as sock:
            sock.settimeout(timeout)
            (opened if sock.connect_ex(("127.0.0.1", int(port))) == 0 else closed).add(int(port))
    return opened, closed


def load_settings(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def default_settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Nova" / "temp" / "routing_settings.json"
    if base.is_file():
        return base
    return Path(__file__).resolve().parents[1] / "routing_settings.json"


def default_selection_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Nova" / "temp" / "profile-selection.json"


def fetch_pac(url=PAC_URL, timeout=5.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Проверить политику KALIOPA")
    parser.add_argument("--settings", default="")
    parser.add_argument("--selection", default="")
    parser.add_argument("--pac", default=PAC_URL)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-ports", action="store_true")
    args = parser.parse_args(argv)
    settings_path = Path(args.settings) if args.settings else default_settings_path()
    selection_path = Path(args.selection) if args.selection else default_selection_path()
    try:
        settings = load_settings(settings_path)
    except Exception as exc:
        print("settings: %s" % exc, file=sys.stderr)
        return 2
    issues = check_settings(settings)
    try:
        selection = load_settings(selection_path)
        issues.extend(check_primary(selection))
    except Exception as exc:
        issues.append("profile-selection недоступен: %s" % exc)
    pac = ""
    try:
        pac = fetch_pac(args.pac)
        issues.extend(check_pac(pac))
    except Exception as exc:
        issues.append("PAC недоступен: %s" % exc)
    if not args.no_ports:
        opened, closed = probe_ports()
        issues.extend(check_ports(opened, closed))
    result = {
        "ok": not issues,
        "settings": str(settings_path),
        "selection": str(selection_path),
        "issues": issues,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print("settings:", settings_path)
        print("selection:", selection_path)
        if issues:
            print("issues:")
            for issue in issues:
                print("  -", issue)
        else:
            print("policy OK: PAC 1370/1371/DIRECT, Telegram WARP, Tor/VLESS reserve")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
