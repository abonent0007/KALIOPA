"""Сбор осиротевших тестовых движков (`winws_test.exe`).

Каждая проверка стратегии запускает свой `winws_test.exe` и снимает его в
`finally`. Если Nova падает или `taskkill` не успевает, процесс остаётся и
держит фильтр WinDivert: следующая проверка получает занятый драйвер, а
пользователь — лишний процесс в диспетчере.

Возраст считается в PowerShell (CIM CreationDate) — на стороне Python не
нужно разбирать формат даты. Имена процессов проверяются регуляркой, поэтому
в команду не попадает произвольная строка.
"""

import os
import re

import nova_win_ps

try:
    DEFAULT_MAX_AGE_SEC = max(60, int(os.environ.get("NOVA_PROCESS_ORPHAN_AGE", "600") or 600))
except ValueError:
    DEFAULT_MAX_AGE_SEC = 600
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
DEFAULT_TIMEOUT = nova_win_ps.DEFAULT_TIMEOUT

__all__ = ["find_orphans", "kill_orphans"]


def _powershell(command, timeout=DEFAULT_TIMEOUT, runner=None):
    run = runner or nova_win_ps.run
    return run(command, timeout=timeout)


def _rows(output):
    return nova_win_ps.json_rows(output)


def find_orphans(names=("winws_test.exe",), max_age_sec=DEFAULT_MAX_AGE_SEC, runner=None):
    """[{"pid", "name", "age_sec"}] для процессов старше порога."""
    safe = [str(name) for name in (names or ()) if SAFE_NAME.match(str(name or ""))]
    if not safe:
        return []
    clause = " or ".join("Name='%s'" % name for name in safe)
    command = (
        "$now = Get-Date; "
        "Get-CimInstance Win32_Process -Filter \"%s\" | ForEach-Object { "
        "[pscustomobject]@{ ProcessId = $_.ProcessId; Name = $_.Name; "
        "AgeSec = [int]((New-TimeSpan -Start $_.CreationDate -End $now).TotalSeconds) } } "
        "| ConvertTo-Json -Compress" % clause
    )
    run = runner or _powershell
    needed = max(0, int(max_age_sec or 0))
    found = []
    for row in _rows(run(command)):
        try:
            pid = int(row.get("ProcessId"))
            age = int(row.get("AgeSec"))
        except (TypeError, ValueError):
            continue
        if age < needed:
            continue
        found.append({"pid": pid, "name": str(row.get("Name") or ""), "age_sec": age})
    return found


def kill_orphans(names=("winws_test.exe",), max_age_sec=DEFAULT_MAX_AGE_SEC, runner=None, log=None):
    """Снять найденные осиротевшие процессы. Возвращает число снятых."""
    say = log if callable(log) else (lambda _text: None)
    try:
        orphans = find_orphans(names, max_age_sec, runner=runner)
    except Exception as exc:
        say("[Cleanup] список процессов не получен: %s" % exc)
        return 0
    killed = 0
    run = runner or _powershell
    for orphan in orphans:
        try:
            run("Stop-Process -Id %d -Force -ErrorAction SilentlyContinue" % int(orphan["pid"]))
            killed += 1
        except Exception:
            continue
    if killed:
        say("[Cleanup] снято осиротевших движков: %d" % killed)
    return killed
