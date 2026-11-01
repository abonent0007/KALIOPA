#!/usr/bin/env python3
"""Статический анализ без внешних линтеров.

Три проверки, которых не хватало в проекте:

1. Неиспользуемые импорты (AST, а не регулярки).
2. Инвентаризация статических данных: URL, IP-литералы, абсолютные пути,
   «магические» порты в строковых и числовых константах.
3. Внешние вызовы без обработки ошибок: `urllib`/`requests`/`socket`/
   `subprocess`/`ctypes.windll`, не находящиеся внутри `try`.

Запуск:
    python tools/static_analysis.py                 # resources + tgrelay + tools + tests
    python tools/static_analysis.py nova.pyw        # отдельные файлы/каталоги
    python tools/static_analysis.py --json          # машинный вывод

Код возврата: 0 — чисто, 1 — есть находки (для CI).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("resources", "tgrelay", "tools", "tests")

URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:\\")
EXTERNAL_DATA_CALLS = {
    "urllib.request.urlopen",
    "urllib.request.urlretrieve",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.request",
    "socket.create_connection",
}
EXTERNAL_SETUP_CALLS = {
    "requests.Session",
    "socket.socket",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_output",
    "os.system",
    "ctypes.windll",
}


@dataclass
class FileReport:
    path: str
    unused_imports: list[dict] = field(default_factory=list)
    static_values: list[dict] = field(default_factory=list)
    unguarded_calls: list[dict] = field(default_factory=list)
    unguarded_setup: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "unused_imports": self.unused_imports,
            "static_values": self.static_values,
            "unguarded_calls": self.unguarded_calls,
            "unguarded_setup": self.unguarded_setup,
        }


def _imported_names(tree: ast.AST) -> dict[str, dict]:
    names: dict[str, dict] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name.split(".")[0]
                names[local] = {"module": alias.name, "line": node.lineno}
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                names[local] = {"module": f"{node.module or ''}.{alias.name}", "line": node.lineno}
    return names


def _used_names(tree: ast.AST) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                used.add(root.id)
    return used


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    cur: ast.AST = node.func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _is_external(name: str) -> bool:
    if name in EXTERNAL_DATA_CALLS or name in EXTERNAL_SETUP_CALLS:
        return True
    return name.startswith("ctypes.windll") or name.startswith("requests.")


def _is_data_call(name: str) -> bool:
    return name in EXTERNAL_DATA_CALLS or (
        name.startswith("requests.") and not name.startswith("requests.Session")
    )


def _guarded_nodes(tree: ast.AST) -> set[int]:
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                guarded.add(id(child))

    # Guard на уровне вызывающего: функция или класс, чей вызов стоит внутри
    # try, считается обработанной — падение всплывёт туда.
    functions = {
        node.name: node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    guarded_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    name = child.func.id
                    if name not in guarded_names and (name in functions or name in classes):
                        guarded_names.add(name)
                        changed = True
    for name in guarded_names:
        unit = functions.get(name) or classes.get(name)
        if unit is not None:
            guarded.update(id(child) for child in ast.walk(unit))
    return guarded


def analyze_source(text: str, path: str) -> FileReport:
    report = FileReport(path=path)
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        report.static_values.append({"line": exc.lineno or 0, "kind": "syntax_error", "value": str(exc.msg)})
        return report

    imported = _imported_names(tree)
    used = _used_names(tree)
    exported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    try:
                        exported = {str(item) for item in ast.literal_eval(node.value)}
                    except (ValueError, TypeError):
                        exported = set()
    is_package_init = Path(path).name == "__init__.py"
    for name, info in sorted(imported.items(), key=lambda item: item[1]["line"]):
        if info["module"].startswith("__future__"):
            continue
        if is_package_init or name in exported:
            continue
        if name not in used:
            report.unused_imports.append({"line": info["line"], "name": name, "module": info["module"]})

    guarded = _guarded_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, str):
                kind = None
                if URL_RE.match(value):
                    kind = "url"
                elif IPV4_RE.match(value):
                    kind = "ip"
                elif WINDOWS_PATH_RE.match(value):
                    kind = "windows_path"
                if kind:
                    report.static_values.append({"line": node.lineno, "kind": kind, "value": value})
            elif isinstance(value, int) and 1024 <= value <= 65535:
                # Порты, а не размеры буферов: степени двойки — почти всегда
                # chunk/buffer, их в инвентарь не берём.
                if value & (value - 1):
                    # ?? ?????? ?????: ????????, ??????, ??????? ???? ? ?????
                    # ???????????? ??????? ? ???? ?????????.
                    report.static_values.append({"line": node.lineno, "kind": "number", "value": value})
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name and _is_external(name) and id(node) not in guarded:
                bucket = report.unguarded_calls if _is_data_call(name) else report.unguarded_setup
                bucket.append({"line": node.lineno, "call": name})
    return report


def iter_python_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        path = Path(target)
        if not path.is_absolute():
            path = BASE_DIR / path
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts))
        elif path.exists():
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Статический анализ Python-файлов проекта")
    parser.add_argument("targets", nargs="*", default=list(DEFAULT_TARGETS))
    parser.add_argument("--json", action="store_true", help="машинный вывод")
    parser.add_argument("--quiet", action="store_true", help="только итоговые числа")
    args = parser.parse_args(argv)

    files = iter_python_files(args.targets or list(DEFAULT_TARGETS))
    reports = [analyze_source(p.read_text(encoding="utf-8", errors="ignore"), str(p)) for p in files]

    total_unused = sum(len(r.unused_imports) for r in reports)
    total_static = sum(len(r.static_values) for r in reports)
    total_calls = sum(len(r.unguarded_calls) for r in reports)
    total_setup = sum(len(r.unguarded_setup) for r in reports)

    if args.json:
        print(
            json.dumps(
                {
                    "files": len(reports),
                    "unused_imports": total_unused,
                    "static_values": total_static,
                    "unguarded_calls": total_calls,
                    "unguarded_setup": total_setup,
                    "reports": [r.as_dict() for r in reports if r.unused_imports or r.unguarded_calls],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if (total_unused or total_calls) else 0

    if not args.quiet:
        for report in reports:
            if not (report.unused_imports or report.unguarded_calls):
                continue
            print(f"\n{report.path}")
            for item in report.unused_imports:
                print(f"  unused import  L{item['line']:<6} {item['name']}  ({item['module']})")
            for item in report.unguarded_calls:
                print(f"  unguarded data  L{item['line']:<6} {item['call']}")
            for item in report.unguarded_setup:
                print(f"  unguarded setup L{item['line']:<6} {item['call']}")

    print(
        f"\nfiles={len(reports)} unused_imports={total_unused} "
        f"static_values={total_static} unguarded_calls={total_calls} unguarded_setup={total_setup}"
    )
    return 1 if (total_unused or total_calls) else 0


if __name__ == "__main__":
    sys.exit(main())
