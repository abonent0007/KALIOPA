"""Probe VLESS profiles with the real nova-xray core and check ChatGPT.

Why not a Python TLS probe: REALITY/uTLS handshakes and the actual routing only
exist inside nova-xray. A Python socket test rejects nodes the core would use.

Usage:
  python tools/vless_chatgpt_probe.py --limit 30 --workers 6
  python tools/vless_chatgpt_probe.py --limit 50 --filter "DE|NL|US|GB|FR|CA|JP"
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
sys.path.insert(0, str(RESOURCES))

import nova_vless  # noqa: E402

APP = Path(os.environ.get("LOCALAPPDATA", "")) / "Nova"
PROFILES = APP / "profiles" / "VLESS"
XRAY = APP / "resources" / "bin" / "nova-xray.exe"
CURL = "curl.exe"
CHATGPT = "https://chatgpt.com/"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def load_nodes(limit: int, pattern: str, exclude_ru: bool):
    nodes = []
    seen = set()
    files = sorted(PROFILES.glob("*.json"))
    random.Random(20261101).shuffle(files)
    for path in files:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        uri = str(obj.get("uri") or "")
        if not uri:
            continue
        node = nova_vless.parse_uri(uri)
        if node is None or node.identity in seen:
            continue
        remark = f"{obj.get('remark') or ''} {path.stem}"
        if exclude_ru and re.search(r"(?i)(^|[^A-Z])(RU|RUS|RUSSIA|🇷🇺)([^A-Z]|$)", remark):
            continue
        if pattern and not re.search(pattern, remark, re.I):
            continue
        seen.add(node.identity)
        nodes.append((path.stem, node))
        if len(nodes) >= limit:
            break
    return nodes


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.15)
    return False


def curl_code(url: str, port: int, timeout: int) -> str:
    proc = subprocess.run(
        [CURL, "-s", "--ssl-no-revoke", "-o", "NUL", "-w", "%{http_code}",
         "--socks5-hostname", f"127.0.0.1:{port}", "--max-time", str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 5, creationflags=NO_WINDOW,
    )
    return (proc.stdout or "").strip() or "000"


def exit_info(port: int) -> str:
    proc = subprocess.run(
        [CURL, "-s", "--max-time", "10", "--socks5-hostname", f"127.0.0.1:{port}",
         "http://ip-api.com/json/?fields=status,countryCode,isp,query"],
        capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW,
    )
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError:
        return ""
    if data.get("status") != "success":
        return ""
    return f"{data.get('countryCode','?')} {data.get('isp','?')} {data.get('query','?')}"


def probe_one(item, chat_timeout: int, url: str = CHATGPT):
    label, node = item
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="nova-vless-") as tmp:
        config = nova_vless.build_xray_config(node, port, log_level="error")
        cfg = Path(tmp) / "config.json"
        ready = Path(tmp) / "ready"
        cfg.write_text(json.dumps(config), encoding="utf-8")
        proc = subprocess.Popen(
            [str(XRAY), "run", "-config", str(cfg), "-ready-file", str(ready)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW,
        )
        try:
            if not wait_port(port, 7.0):
                return {"label": label, "code": "no-start", "exit": "", "node": node.endpoint}
            code = curl_code(url, port, chat_timeout)
            info = exit_info(port) if (url == CHATGPT and code in {"200", "302", "307"}) else ""
            return {"label": label, "code": code, "exit": info, "node": node.endpoint}
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--filter", default="")
    parser.add_argument("--exclude-ru", action="store_true")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--url", default=CHATGPT)
    args = parser.parse_args()

    if not XRAY.exists():
        print("nova-xray.exe not found:", XRAY)
        return 2
    nodes = load_nodes(args.limit, args.filter, args.exclude_ru)
    print(f"probing {len(nodes)} nodes, workers={args.workers}")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(probe_one, item, args.timeout, args.url): item for item in nodes}
        for future in concurrent.futures.as_completed(futures):
            try:
                row = future.result()
            except Exception as exc:
                row = {"label": str(futures[future][0]), "code": f"error:{type(exc).__name__}", "exit": ""}
            results.append(row)
            print(f"  {row.get('code','?'):>8}  {row.get('exit',''):<28}  {row.get('label','')[:44]}")

    ok = [row for row in results if row.get("code") == "200"]
    print(f"\nchatgpt 200: {len(ok)} / {len(results)}")
    for row in ok:
        print("  OK", row.get("exit"), row.get("label"), row.get("node"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
