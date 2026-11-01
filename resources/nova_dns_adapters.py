"""Снимок DNS-серверов адаптеров и их восстановление.

Единственная причина существования модуля — безопасно вернуть систему в
исходное состояние после локального DoH-резолвера. Снимок пишется на диск
*до* первого `Set-DnsClientServerAddress`: если Nova упадёт, следующий запуск
увидит файл и восстановит адреса сам (`recover`).

PowerShell вызывается без `shell=True`; индекс адаптера и адреса проверяются,
поэтому в команду не может попасть произвольная строка.
"""

import ipaddress
import json
import os

import nova_win_ps

SNAPSHOT_FILENAME = "dns_adapters.json"
DEFAULT_TIMEOUT = nova_win_ps.DEFAULT_TIMEOUT

__all__ = [
    "SNAPSHOT_FILENAME", "snapshot", "save", "load", "apply", "restore",
    "restore_file", "recover",
]


def _powershell(command, timeout=DEFAULT_TIMEOUT, runner=None):
    run = runner or nova_win_ps.run
    return run(command, timeout=timeout)


def snapshot(runner=None):
    """[{"index", "alias", "servers"}] для IPv4-адаптеров с непустым DNS."""
    run = runner or _powershell
    output = run(
        "Get-DnsClientServerAddress -AddressFamily IPv4 | "
        "Where-Object { $_.ServerAddresses } | "
        "Select-Object InterfaceIndex,InterfaceAlias,ServerAddresses | ConvertTo-Json -Compress"
    )
    data = nova_win_ps.json_rows(output)
    rows = []
    for row in data:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("InterfaceIndex"))
        except (TypeError, ValueError):
            continue
        servers = row.get("ServerAddresses") or []
        if isinstance(servers, str):
            servers = [servers]
        rows.append({
            "index": index,
            "alias": str(row.get("InterfaceAlias") or ""),
            "servers": [str(server) for server in servers if str(server or "").strip()],
        })
    return rows


def save(path, rows):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"adapters": list(rows or [])}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("adapters") if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else []


def _valid_ip(value):
    try:
        return str(ipaddress.ip_address(str(value)))
    except ValueError:
        raise ValueError("не IP-адрес: %r" % (value,))


def _set(index, servers, runner=None):
    run = runner or _powershell
    index = int(index)
    if servers:
        literals = ",".join("'%s'" % _valid_ip(server) for server in servers)
        run("Set-DnsClientServerAddress -InterfaceIndex %d -ServerAddresses @(%s)" % (index, literals))
    else:
        run("Set-DnsClientServerAddress -InterfaceIndex %d -ResetServerAddresses" % index)


def apply(rows, dns_ip, runner=None):
    """Поставить `dns_ip` на каждый адаптер из снимка. Возвращает число изменённых."""
    address = _valid_ip(dns_ip)
    changed = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index"))
        except (KeyError, TypeError, ValueError):
            continue
        _set(index, [address], runner)
        changed += 1
    return changed


def restore(rows, runner=None):
    """Вернуть каждому адаптеру его прежние серверы (пустой список — сброс)."""
    restored = 0
    for row in reversed(list(rows or [])):
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index"))
        except (KeyError, TypeError, ValueError):
            continue
        servers = [str(server) for server in (row.get("servers") or []) if str(server or "").strip()]
        _set(index, servers, runner)
        restored += 1
    return restored


def restore_file(path, runner=None):
    """Восстановить из файла и удалить его. False, если файла нет."""
    if not os.path.exists(path):
        return False
    rows = load(path)
    restore(rows, runner)
    try:
        os.remove(path)
    except OSError:
        pass
    return True


def recover(temp_dir, runner=None):
    """Довести до конца восстановление, прерванное падением прошлого запуска."""
    return restore_file(os.path.join(str(temp_dir), SNAPSHOT_FILENAME), runner)
