"""Каталог страновых точек входа для разового AWG-генератора (Custom AWG).

Владелец сам вписывает свои серверы: `temp/warp-countries.json`. Запись — только
название, хост, порт и ISO-код, без ключей и абсолютных путей (I19). Пустой хост
у страны (или `id="any"`) означает «любая» — генератор уходит на обычный скан
Cloudflare, как до появления каталога.

Файл читается терпимо: битый JSON и мусорные записи не роняют генератор —
незнакомые поля отбрасываются, числа зажимаются в диапазон, а записи без id или
с негодным хостом выбрасываются. Запись атомарна (`.tmp` + `os.replace`).
"""

from __future__ import annotations

__all__ = [
    "FILENAME",
    "TEMP_DIRNAME",
    "ANY_ID",
    "DEFAULT_CATALOG",
    "normalize_entry",
    "normalize",
    "load",
    "save",
    "by_id",
    "resolve",
    "label",
]

import json
import os
import re

FILENAME = "warp-countries.json"
TEMP_DIRNAME = "temp"

# Единственная запись по умолчанию: страна не задана — точку входа ищет сканер.
ANY_ID = "any"

DEFAULT_CATALOG = (
    {"id": ANY_ID, "title": "Любая (Cloudflare anycast)", "host": "", "port": 0,
     "iso": "", "note": "авто-скан точек входа"},
)

_HOST_RE = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")
_ISO_RE = re.compile(r"^[A-Za-z]{2}$")
_ID_RE = re.compile(r"[^a-z0-9_-]+")


def _as_int(value, default, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def normalize_entry(raw) -> dict | None:
    """Одна запись каталога или None, если она непригодна.

    Пригодна — с непустым `id` и либо пустым хостом («любая»), либо хостом,
    похожим на имя/IP. Порт 0 допустим: это «любой стандартный порт».
    """
    if not isinstance(raw, dict):
        return None
    cid = _ID_RE.sub("-", str(raw.get("id") or "").strip().lower()).strip("-")
    if not cid:
        return None
    host = str(raw.get("host") or "").strip().rstrip(".")
    if host and not _HOST_RE.match(host):
        return None
    iso = str(raw.get("iso") or "").strip().upper()
    if iso and not _ISO_RE.match(iso):
        iso = ""
    note = str(raw.get("note") or "").strip()[:80]
    return {
        "id": cid,
        "title": str(raw.get("title") or "").strip()[:60] or cid.upper(),
        "host": host,
        "port": _as_int(raw.get("port"), 0, 0, 65535),
        "iso": iso,
        "note": note,
    }


def normalize(rows) -> list[dict]:
    """Список записей без дублей по `id`; первой всегда идёт `any`, даже если её нет в файле."""
    out: list[dict] = []
    seen = set()
    for raw in rows or ():
        entry = normalize_entry(raw)
        if entry is None or entry["id"] in seen:
            continue
        seen.add(entry["id"])
        out.append(entry)
    default = by_id(out, ANY_ID)
    if default is None:
        out.insert(0, dict(DEFAULT_CATALOG[0]))
    elif out[0]["id"] != ANY_ID:
        out.remove(default)
        out.insert(0, default)
    return out


def _path(base_dir) -> str:
    return os.path.join(str(base_dir), TEMP_DIRNAME, FILENAME)


def load(base_dir) -> list[dict]:
    """Каталог с диска; отсутствующий или битый файл — каталог по умолчанию."""
    try:
        with open(_path(base_dir), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return [dict(item) for item in DEFAULT_CATALOG]
    rows = payload.get("countries") if isinstance(payload, dict) else payload
    return normalize(rows if isinstance(rows, list) else [])


def save(base_dir, rows) -> list[dict]:
    """Атомарная запись каталога; возвращает нормализованный список."""
    data = normalize(rows)
    path = _path(base_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"version": 1, "countries": data}, handle,
                      ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        return data
    return data


def by_id(rows, country_id) -> dict | None:
    wanted = str(country_id or "").strip().lower()
    for row in rows or ():
        if str(row.get("id") or "").strip().lower() == wanted:
            return row
    return None


def resolve(rows, country_id) -> tuple[str, int]:
    """`(host, port)` страны; `("", 0)` для «любой» и для неизвестного id."""
    row = by_id(rows, country_id)
    if row is None or row.get("id") == ANY_ID:
        return "", 0
    host = str(row.get("host") or "").strip()
    port = _as_int(row.get("port"), 0, 0, 65535)
    return host, port


def label(row) -> str:
    """«🇫🇮 Финляндия · fi.example:500» — так запись выглядит в списке и в журле."""
    if not isinstance(row, dict):
        return ""
    text = str(row.get("title") or row.get("id") or "").strip()
    host = str(row.get("host") or "").strip()
    if host:
        text += f" · {host}:{int(row.get('port') or 0)}"
    elif str(row.get("id") or "") == ANY_ID:
        text += " · авто-скан"
    return text
