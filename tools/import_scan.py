"""Проверка локальных импортов: каждый `nova_*` и `tgrelay` обязан существовать.

Зачем отдельно от линтера: PyInstaller-сборка складывает `resources/` рядом с
`nova.pyw`, и опечатка в имени модуля не ломает `py_compile` — она ломает запуск
уже установленной программы. Скрипт ловит такие импорты до сборки.

Использование:
  python tools/import_scan.py            # весь проект
  python tools/import_scan.py --diff     # только изменённые относительно HEAD файлы
"""

from __future__ import annotations

import argparse
import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"


def local_target(module: str):
    """True/False для локального модуля, None для внешнего."""
    top = str(module or "").split(".", 1)[0]
    if top.startswith("nova_"):
        return (RESOURCES / (top + ".py")).exists()
    if top == "tgrelay":
        return (ROOT / "tgrelay" / "__init__.py").exists()
    return None


def optional_imports(tree):
    """Импорты внутри try/except: их отсутствие допустимо (guarded import)."""
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    guarded.add(id(child))
    return guarded


def scan_file(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    except SyntaxError as exc:
        return [{"path": str(path), "line": exc.lineno or 0, "module": "", "reason": "syntax: %s" % exc.msg}]
    guarded = optional_imports(tree)
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
            line = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # относительный импорт внутри пакета
                continue
            modules = [node.module or ""]
            line = node.lineno
        else:
            continue
        for module in modules:
            exists = local_target(module)
            if exists is False:
                problems.append({
                    "path": str(path.relative_to(ROOT)),
                    "line": line,
                    "module": module,
                    "reason": "optional" if id(node) in guarded else "missing",
                })
    return problems


def changed_files():
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=20
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [ROOT / line.strip() for line in out.splitlines() if line.strip().endswith(".py")]


def collect(diff=False):
    if diff:
        files = [path for path in changed_files() if path.exists()]
    else:
        files = [
            path for path in ROOT.rglob("*.py")
            if "__pycache__" not in path.parts and ".opencode" not in path.parts
        ]
    return sorted(set(files))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Проверка локальных импортов Nova")
    parser.add_argument("--diff", action="store_true", help="только изменённые файлы")
    args = parser.parse_args(argv)
    files = collect(diff=args.diff)
    problems = []
    for path in files:
        problems.extend(scan_file(path))
    missing = [p for p in problems if p["reason"] != "optional"]
    optional = [p for p in problems if p["reason"] == "optional"]
    for item in problems:
        print(f"{item['path']}:{item['line']}  {item['module']}  ({item['reason']})")
    print(f"files={len(files)} missing={len(missing)} optional_missing={len(optional)}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
