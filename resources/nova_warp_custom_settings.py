"""Настройки разового генератора WARP в Custom AWG.

Один профиль в `profiles/Custom` создаёт `nova_warp_generator.generate_custom_one`.
Этот модуль хранит то, что владелец может поменять до нажатия «Сгенерировать»:
пресет, точку входа, DNS, MTU, keepalive, имя прикрытия и параметры джанка.

Файл — `temp/warp-custom-settings.json`: только числа, имена и адреса, без ключей
и без абсолютных путей. Чтение терпимо к мусору (старая версия файла, ручная
правка): неизвестные поля отбрасываются, числа зажимаются в допустимый диапазон,
а непрошедшие проверку значения откатываются к дефолту — генератор не должен
падать из-за настроек.

Пресеты:
- `optimal` — то, что проверено живыми прогонами: MTU 1280, два DNS, случайное
  прикрытие, до двух точек входа и трёх имён прикрытия;
- `fast` — меньше служебного джанка и три точки входа: генератор пробует больше
  кандидатов и оставляет первый, который дважды подряд отдал 204;
- `compat` — MTU 1240 и четыре DNS: для сетей, где крупные пакеты дробятся, а
  первый DNS-сервер недоступен.

`custom` — всё вручную; пустые поля означают «как в optimal».
"""

from __future__ import annotations

__all__ = [
    "FILENAME",
    "DEFAULTS",
    "PRESETS",
    "PRESET_ORDER",
    "normalize",
    "apply_preset",
    "resolve",
    "load",
    "save",
]

import json
import os
import re
from typing import Any

FILENAME = "warp-custom-settings.json"
TEMP_DIRNAME = "temp"

MTU_MIN = 576
MTU_MAX = 1420
KEEPALIVE_MAX = 3600
JUNK_COUNT_RANGE = (1, 10)
JUNK_SIZE_RANGE = (10, 200)
DNS_DEFAULT = "1.1.1.1, 1.0.0.1"
DNS_FULL = "1.1.1.1, 1.0.0.1, 2606:4700:4700::1111, 2606:4700:4700::1001"
SNI_DEFAULT = "yastatic.net"

PRESET_ORDER = ("optimal", "fast", "compat", "custom")

DEFAULTS = {
    "preset": "optimal",
    "endpoint_mode": "auto",
    "endpoint_host": "",
    "endpoint_port": 2408,
    "dns": DNS_DEFAULT,
    "mtu": 1280,
    "keepalive": 25,
    "sni": "",
    "jc": 0,
    "jmin": 0,
    "jmax": 0,
    "endpoint_attempts": 2,
    "sni_attempts": 3,
}

PRESETS: dict[str, dict[str, Any]] = {
    "optimal": {
        "title": "Оптимальный",
        "hint": "Проверено живыми прогонами: MTU 1280, два DNS, случайное прикрытие, "
                "до двух точек входа.",
        "values": {
            "endpoint_mode": "auto", "dns": DNS_DEFAULT, "mtu": 1280, "keepalive": 25,
            "sni": "", "jc": 0, "jmin": 0, "jmax": 0,
            "endpoint_attempts": 2, "sni_attempts": 3,
        },
    },
    "fast": {
        "title": "Быстрый отклик",
        "hint": "Меньше служебного джанка и три точки входа: генератор перебирает больше "
                "кандидатов и оставляет первый, который дважды отдал 204.",
        "values": {
            "endpoint_mode": "auto", "dns": "1.1.1.1", "mtu": 1280, "keepalive": 25,
            "sni": SNI_DEFAULT, "jc": 3, "jmin": 30, "jmax": 55,
            "endpoint_attempts": 3, "sni_attempts": 2,
        },
    },
    "compat": {
        "title": "Совместимость",
        "hint": "MTU 1240 и четыре DNS: для сетей, где крупные пакеты дробятся, а первый "
                "DNS-сервер недоступен.",
        "values": {
            "endpoint_mode": "auto", "dns": DNS_FULL, "mtu": 1240, "keepalive": 25,
            "sni": "", "jc": 0, "jmin": 0, "jmax": 0,
            "endpoint_attempts": 1, "sni_attempts": 4,
        },
    },
}

_HOST_RE = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")
_SNI_RE = re.compile(r"^[A-Za-z0-9.-]{1,250}$")
_DNS_RE = re.compile(r"^[A-Za-z0-9.:_-]{1,64}$")


def _int(value, default, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _dns_list(value):
    parts = [part.strip() for part in str(value or "").replace(";", ",").split(",")]
    clean = [part for part in parts if part and _DNS_RE.match(part)]
    return ", ".join(clean[:4])


def normalize(raw) -> dict:
    """A settings dict safe to hand to the generator; never raises."""
    data = dict(DEFAULTS)
    if isinstance(raw, dict):
        data.update({key: raw[key] for key in DEFAULTS if key in raw})
    preset = str(data.get("preset") or "optimal").strip().lower()
    data["preset"] = preset if preset in PRESET_ORDER else "optimal"
    mode = str(data.get("endpoint_mode") or "auto").strip().lower()
    data["endpoint_mode"] = mode if mode in ("auto", "manual") else "auto"
    host = str(data.get("endpoint_host") or "").strip()
    data["endpoint_host"] = host if host and _HOST_RE.match(host) else ""
    data["endpoint_port"] = _int(data.get("endpoint_port"), 2408, 1, 65535)
    data["dns"] = _dns_list(data.get("dns")) or DNS_DEFAULT
    data["mtu"] = _int(data.get("mtu"), 1280, MTU_MIN, MTU_MAX)
    data["keepalive"] = _int(data.get("keepalive"), 25, 0, KEEPALIVE_MAX)
    sni = str(data.get("sni") or "").strip().rstrip(".")
    data["sni"] = sni if sni and _SNI_RE.match(sni) else ""
    count = _int(data.get("jc"), 0, 0, JUNK_COUNT_RANGE[1])
    minimum = _int(data.get("jmin"), 0, 0, JUNK_SIZE_RANGE[1])
    maximum = _int(data.get("jmax"), 0, 0, JUNK_SIZE_RANGE[1])
    # Either all three are set (owner pinned the junk) or all three are zero (random).
    if not (count and minimum and maximum) or maximum < minimum:
        count = minimum = maximum = 0
    data["jc"], data["jmin"], data["jmax"] = count, minimum, maximum
    data["endpoint_attempts"] = _int(data.get("endpoint_attempts"), 2, 1, 3)
    data["sni_attempts"] = _int(data.get("sni_attempts"), 3, 1, 4)
    return data


def apply_preset(preset: str, current=None) -> dict:
    """Values of `preset` over `current`; `custom` keeps everything as it is."""
    data = normalize(current)
    name = str(preset or "").strip().lower()
    if name == "custom":
        data["preset"] = "custom"
        return data
    if name in PRESETS:
        host = data.get("endpoint_host", "")
        data.update(PRESETS[name]["values"])
        data["preset"] = name
        data["endpoint_host"] = host
        return normalize(data)
    return data


def resolve(settings) -> dict:
    """Keyword arguments for `nova_warp_generator.generate_custom_one`."""
    data = normalize(settings)
    host, port = "", 0
    if data["endpoint_mode"] == "manual" and data["endpoint_host"]:
        host, port = data["endpoint_host"], data["endpoint_port"]
    junk = None
    if data["jc"] and data["jmin"] and data["jmax"]:
        junk = (data["jc"], data["jmin"], data["jmax"])
    return {
        "host": host,
        "port": port,
        "dns": data["dns"],
        "mtu": data["mtu"],
        "keepalive": data["keepalive"],
        "sni": data["sni"],
        "junk": junk,
        "endpoint_attempts": data["endpoint_attempts"],
        "sni_attempts": data["sni_attempts"],
    }


def _path(base_dir) -> str:
    return os.path.join(str(base_dir), TEMP_DIRNAME, FILENAME)


def load(base_dir) -> dict:
    """Saved settings or the defaults; a broken file is not an error."""
    try:
        with open(_path(base_dir), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return dict(DEFAULTS)
    return normalize(raw)


def save(base_dir, settings) -> dict:
    """Write the normalized settings; returns what was written."""
    data = normalize(settings)
    path = _path(base_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        return data
    return data
