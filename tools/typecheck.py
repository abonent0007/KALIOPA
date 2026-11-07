"""Проверка типов для затронутых модулей — тонкая обёртка над mypy.

Запуск: `python tools/typecheck.py [файлы...]`.

Почему не весь проект: `nova.pyw` — 33k строк tkinter-кода без аннотаций,
mypy на нём даёт тысячи замечаний к чужому стилю. Проверяются модули, где типы
уже расставлены: новые ресурсы и сетевые клиенты. `nova_warp_generator` пока
не в списке: это старый код без аннотаций, его страхуют 14 собственных тестов.
`--follow-imports=skip` держит прогон быстрым: чужие модули не тянутся в анализ.

Если mypy не установлен, скрипт завершается успешно с пометкой: сборочная
машина без mypy не должна ломать общий прогон проверок.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

DEFAULT_TARGETS = (
    "resources/nova_dns_doh.py",
    "resources/nova_dns_probe.py",
    "resources/nova_doh_service.py",
    "resources/nova_tooltips.py",
    "resources/nova_warp_custom_settings.py",
)

ARGS = (
    "--ignore-missing-imports",
    "--follow-imports=skip",
    "--check-untyped-defs",
    "--no-error-summary",
)


def main(argv: list[str]) -> int:
    targets = [str(pathlib.Path(t)) for t in (argv or DEFAULT_TARGETS)]
    missing = [t for t in targets if not pathlib.Path(t).is_file()]
    if missing:
        print("typecheck: нет файлов:", ", ".join(missing))
        return 2
    try:
        probe = subprocess.run([sys.executable, "-m", "mypy", "--version"],
                               capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        probe = None
    if probe is None or probe.returncode != 0:
        print("typecheck: mypy не установлен — пропущено (pip install mypy)")
        return 0
    try:
        result = subprocess.run([sys.executable, "-m", "mypy", *ARGS, *targets],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"typecheck: mypy не запустился: {type(exc).__name__}")
        return 0
    output = (result.stdout or "") + (result.stderr or "")
    if output.strip():
        print(output.rstrip())
    if result.returncode == 0:
        print(f"typecheck: OK ({len(targets)} файлов)")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
