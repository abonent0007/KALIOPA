"""Проверка обновлений модулей KALIOPA по манифесту в docs/agents/module-updates.md.

Скрипт не обновляет ничего сам: он только сверяет `current` из MD с последним
релизом/тегом источника и печатает список. Это защита от «апдейт вслепую»:
решение и тесты остаются за человеком/агентом.

Использование:
  python tools/check_module_updates.py            # обычная проверка (кэш 12 ч)
  python tools/check_module_updates.py --force    # без кэша
  python tools/check_module_updates.py --quiet    # одна строка для старта сессии
  python tools/check_module_updates.py --json     # машинный вывод
  python tools/check_module_updates.py --fail-on-update  # exit 2, если есть обновления
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES_MD = ROOT / "docs" / "agents" / "module-updates.md"
CACHE_PATH = ROOT / "temp" / "module_updates_cache.json"
BLOCK_RE = re.compile(r"```json module-sources\s*(\{.*?\})\s*```", re.S)
VERSION_RE = re.compile(r"\d+(?:\.\d+)*")


def load_sources(path: Path = SOURCES_MD) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    match = BLOCK_RE.search(text)
    if not match:
        raise ValueError("в %s нет блока ```json module-sources" % path)
    data = json.loads(match.group(1))
    if not isinstance(data, dict) or not isinstance(data.get("modules"), list):
        raise ValueError("module-sources должен содержать список modules")
    return data


def version_key(value: str):
    """'v26.10.31' -> (26, 10, 31); нечисловые версии сравниваются строкой."""
    text = str(value or "").strip().lower().lstrip("v")
    numbers = VERSION_RE.findall(text)
    if not numbers:
        return (text,)
    return tuple(int(part) for part in numbers[0].split("."))


def is_newer(latest: str, current: str) -> bool:
    try:
        return version_key(latest) > version_key(current)
    except TypeError:
        return str(latest).strip().lower() != str(current).strip().lower()


def _github_token() -> str:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            return value
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    data = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    return str(data.get("password") or "").strip()


def _http_json(url: str, token: str = "", timeout: float = 20.0):
    headers = {"User-Agent": "Kaliopa-ModuleCheck", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 403 and "rate limit" in (exc.reason or "").lower():
            raise RuntimeError("GitHub rate limit; задайте GITHUB_TOKEN или повторите позже") from exc
        raise


def _github_latest(module: dict, token: str) -> str:
    repo = str(module.get("repo") or "").strip()
    if not repo:
        raise ValueError("не указан repo")
    kind = str(module.get("kind") or "")
    if kind == "github-release":
        try:
            data = _http_json("https://api.github.com/repos/%s/releases/latest" % repo, token)
            tag = str(data.get("tag_name") or "").strip()
            if tag:
                return tag
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
    data = _http_json("https://api.github.com/repos/%s/tags?per_page=10" % repo, token)
    if isinstance(data, list):
        for tag in data:
            name = str((tag or {}).get("name") or "").strip()
            if name:
                return name
    raise RuntimeError("нет релизов/тегов")


def _pypi_latest(package: str) -> str:
    data = _http_json("https://pypi.org/pypi/%s/json" % package)
    return str((data.get("info") or {}).get("version") or "").strip()


def _read_cache() -> dict:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(data: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def _cached(cache: dict, module_id: str, max_age: float):
    row = (cache.get("results") or {}).get(module_id)
    if not isinstance(row, dict):
        return None
    if time.time() - float(row.get("checked_at") or 0) > max_age:
        return None
    latest = str(row.get("latest") or "").strip()
    return latest or None


def check_module(module: dict, token: str, cache: dict, max_age: float, force: bool):
    module_id = str(module.get("id") or module.get("name") or "?")
    current = str(module.get("current") or "").strip()
    kind = str(module.get("kind") or "").strip().lower()
    if kind == "manual":
        return {"id": module_id, "name": module.get("name", module_id), "current": current,
                "latest": "", "status": "manual", "error": ""}
    if not force:
        cached = _cached(cache, module_id, max_age)
        if cached:
            return _evaluate(module_id, module, cached, source="cache")
    try:
        if kind in ("github-release", "github-tags"):
            latest = _github_latest(module, token)
        elif kind == "pypi":
            latest = _pypi_latest(str(module.get("package") or module_id))
        else:
            return {"id": module_id, "name": module.get("name", module_id), "current": current,
                    "latest": "", "status": "manual", "error": "неизвестный kind=%s" % kind}
    except Exception as exc:
        stale = _cached(cache, module_id, 10 ** 9)
        if stale:
            row = _evaluate(module_id, module, stale, source="stale-cache")
            row["error"] = str(exc)
            return row
        return {"id": module_id, "name": module.get("name", module_id), "current": current,
                "latest": "", "status": "error", "error": str(exc)}
    cache.setdefault("results", {})[module_id] = {"latest": latest, "checked_at": time.time()}
    return _evaluate(module_id, module, latest)


def _evaluate(module_id: str, module: dict, latest: str, source: str = "live"):
    current = str(module.get("current") or "").strip()
    if is_newer(latest, current):
        status = "update"
    elif str(latest).strip().lower().lstrip("v") == current.lower().lstrip("v"):
        status = "current"
    else:
        status = "newer-local" if is_newer(current, latest) else "current"
    return {"id": module_id, "name": module.get("name", module_id), "current": current,
            "latest": latest, "status": status, "error": "", "source": source}


def run_checks(sources: dict, token: str = "", force: bool = False):
    cache = _read_cache()
    max_age = max(1.0, float(sources.get("cache_hours", 12))) * 3600.0
    rows = []
    for module in sources.get("modules", []):
        if not isinstance(module, dict):
            continue
        if str(module.get("kind") or "").lower() == "pypi":
            packages = module.get("packages") or {}
            if not isinstance(packages, dict):
                continue
            for package, current in packages.items():
                single = dict(module)
                single.update({"id": "%s:%s" % (module.get("id", "pypi"), package),
                               "name": package, "current": current, "kind": "pypi", "package": package})
                rows.append(check_module(single, token, cache, max_age, force))
        else:
            rows.append(check_module(module, token, cache, max_age, force))
    cache["checked_at"] = time.time()
    _write_cache(cache)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Проверить обновления модулей KALIOPA")
    parser.add_argument("--force", action="store_true", help="игнорировать кэш")
    parser.add_argument("--quiet", action="store_true", help="одна итоговая строка")
    parser.add_argument("--json", action="store_true", help="машинный вывод")
    parser.add_argument("--fail-on-update", action="store_true", help="exit 2 при найденных обновлениях")
    args = parser.parse_args(argv)
    try:
        sources = load_sources()
    except Exception as exc:
        print("module-sources: %s" % exc, file=sys.stderr)
        return 2
    token = _github_token()
    rows = run_checks(sources, token=token, force=args.force)
    updates = [row for row in rows if row["status"] == "update"]
    errors = [row for row in rows if row["status"] == "error"]
    manual = [row for row in rows if row["status"] == "manual"]
    if args.json:
        print(json.dumps({"rows": rows, "updates": len(updates), "errors": len(errors)}, ensure_ascii=False, indent=1))
    elif args.quiet:
        names = ", ".join(row["id"] for row in updates[:6])
        extra = " (+%d)" % (len(updates) - 6) if len(updates) > 6 else ""
        print("module updates: %d%s | manual: %d | errors: %d%s" % (
            len(updates), extra, len(manual), len(errors),
            (" | " + names) if names else "",
        ))
    else:
        print("%-28s %-18s %-18s %s" % ("module", "current", "latest", "status"))
        for row in rows:
            print("%-28s %-18s %-18s %s%s" % (
                row["id"][:28], (row["current"] or "—")[:18], (row["latest"] or "—")[:18],
                row["status"], (" (" + row["error"] + ")") if row.get("error") else "",
            ))
        print("\nupdates=%d manual=%d errors=%d" % (len(updates), len(manual), len(errors)))
    if args.fail_on_update and updates:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
