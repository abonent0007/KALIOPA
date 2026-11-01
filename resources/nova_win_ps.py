"""Единая точка запуска PowerShell для служебных модулей Nova.

`nova_dns_adapters` и `nova_process_hygiene` одинаково запускали `powershell.exe`,
одинаково теряли stderr и одинаково разбирали `ConvertTo-Json`. Копии уже начали
расходиться, поэтому запуск и разбор вынесены сюда: одно место для таймаута,
`CREATE_NO_WINDOW` и текста ошибки.
"""

import json
import subprocess

DEFAULT_TIMEOUT = 25.0

__all__ = ["DEFAULT_TIMEOUT", "run", "json_rows"]


def run(command, timeout=DEFAULT_TIMEOUT):
    """Выполнить команду PowerShell и вернуть stdout; ошибка — RuntimeError."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", str(command)],
            capture_output=True, text=True, timeout=timeout, creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("powershell не запущен: %s" % exc) from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "powershell failed").strip()[:300])
    return proc.stdout or ""


def json_rows(output):
    """`ConvertTo-Json` -> список словарей; пустой вывод -> []."""
    text = str(output or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError("powershell вернул не JSON: %s" % exc) from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("powershell вернул не список объектов")
    return [row for row in data if isinstance(row, dict)]
