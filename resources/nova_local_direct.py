"""TLDs that are local enough to go DIRECT unless a list says otherwise."""

from __future__ import annotations

import os

DEFAULT_LOCAL_DIRECT_TLDS = (
    ".ru",
    ".su",
    ".рф",
    ".xn--p1ai",
    ".москва",
    ".xn--80adxhks",
    ".moscow",
    ".рус",
    ".xn--p1acf",
    ".дети",
    ".xn--d1acj3b",
    ".tatar",
)


def _normalize_tld(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if not text.startswith("."):
        text = "." + text
    try:
        ascii_label = text[1:].encode("idna").decode("ascii")
        if ascii_label:
            text = "." + ascii_label
    except Exception:
        pass
    return text


def local_direct_tlds(environ=None):
    env = environ if environ is not None else os.environ
    values: list[str] = list(DEFAULT_LOCAL_DIRECT_TLDS)
    raw = str(env.get("NOVA_LOCAL_DIRECT_TLDS", "") or "")
    for item in raw.split(","):
        tld = _normalize_tld(item)
        if tld and tld not in values:
            values.append(tld)
    return tuple(values)


def is_local_direct(host, tlds=None):
    value = str(host or "").strip().lower().rstrip(".")
    if not value:
        return False
    for tld in tlds or local_direct_tlds():
        if value == tld[1:] or value.endswith(tld):
            return True
    return False
