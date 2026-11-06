"""Subscription metadata: the headers and `#` lines that describe a list.

A subscription answers with more than a body. Panels (3x-ui among them) send
`Subscription-Userinfo`, `Profile-Update-Interval`, `Profile-Title` — often as
`base64:<...>` — plus `Support-Url` and `Profile-Web-Page-Url`; the same fields
may be repeated at the top of the body as `#profile-title:`-style comments.

This module turns both spellings into one JSON-safe dict. It is deliberately
passive: it never decides whether a subscription is enabled, never changes the
refresh interval, and never logs a URL. The caller stores the dict in the
registry and the window decides what to show.
"""

import base64
import binascii
import re

__all__ = [
    "MIN_INTERVAL_HOURS", "MAX_INTERVAL_HOURS", "MAX_TITLE_CHARS", "MAX_URL_CHARS",
    "MAX_ANNOUNCE_CHARS", "parse_userinfo", "decode_profile_title", "parse_headers",
    "parse_body_metadata", "sanitize_provider", "merge_provider",
]

MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 24 * 7
MAX_TITLE_CHARS = 160
MAX_URL_CHARS = 2048
MAX_ANNOUNCE_CHARS = 500
MAX_BYTES = (1 << 63) - 1

_USERINFO_RE = re.compile(r"(?i)\b(upload|download|total|expire)\s*[=:]\s*(-?\d+)")
_METADATA_RE = re.compile(r"^\s*#\s*([a-zA-Z][a-zA-Z0-9-]*)\s*:\s*(.*?)\s*$")
_SPACE_RE = re.compile(r"\s+")


def _clean_text(value, limit):
    text = str(value or "").strip()
    if not text:
        return ""
    text = _SPACE_RE.sub(" ", text)
    return text[:limit]


def _clamp_int(value, low=0, high=MAX_BYTES):
    try:
        if isinstance(value, bool):
            number = int(value)
        elif isinstance(value, int):
            number = value
        elif isinstance(value, float):
            number = int(value)
        else:
            number = int(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return max(low, min(high, number))


def _safe_url(value):
    """An http(s) URL, or "". Anything else is not opened by the window."""
    text = _clean_text(value, MAX_URL_CHARS)
    return text if text.lower().startswith(("http://", "https://")) else ""


def _interval(value):
    hours = _clamp_int(value, MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS)
    return hours


def parse_userinfo(value):
    """`upload=1; download=2; total=3; expire=4` -> dict, or None when absent.

    Only the keys that are actually present are kept. That matters: a header
    with `expire` but no `total` does not mean "unlimited", it means "the panel
    did not say", and the window must not print a false "безлимит".
    """
    if isinstance(value, dict):
        text = "; ".join("%s=%s" % (key, value[key]) for key in value)
    else:
        text = str(value or "")
    if not text.strip():
        return None
    found = {}
    for name, raw in _USERINFO_RE.findall(text):
        number = _clamp_int(raw, 0, MAX_BYTES)
        if number is None:
            continue
        found[name.lower()] = number
    if "expire" in found:
        # Some panels send milliseconds; Xray/3x-ui send seconds. 10^12 seconds
        # is well past any real date, so a larger value is unambiguously ms.
        if found["expire"] > 1_000_000_000_000:
            found["expire"] //= 1000
    return found or None


def decode_profile_title(value):
    """A `Profile-Title` value -> text. 3x-ui prefixes it with `base64:`."""
    text = str(value or "").strip()
    if not text:
        return ""
    if text[:7].lower() == "base64:":
        payload = text[7:].strip()
        padded = payload + "=" * (-len(payload) % 4)
        for decoder in (lambda payload: base64.b64decode(payload, validate=False),
                        base64.urlsafe_b64decode):
            try:
                raw = decoder(padded)
                decoded = raw.decode("utf-8")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                continue
            cleaned = _clean_text(decoded, MAX_TITLE_CHARS)
            if cleaned:
                return cleaned
    return _clean_text(text, MAX_TITLE_CHARS)


def parse_headers(headers):
    """HTTP response headers -> provider dict. Unknown headers are ignored."""
    if not headers:
        return {}
    try:
        items = {str(key).strip().lower(): value for key, value in headers.items()}
    except AttributeError:
        return {}
    provider = {}
    title = decode_profile_title(items.get("profile-title"))
    if title:
        provider["title"] = title
    interval = _interval(items.get("profile-update-interval"))
    if interval:
        provider["update_interval_hours"] = interval
    userinfo = parse_userinfo(items.get("subscription-userinfo"))
    if userinfo:
        provider["userinfo"] = userinfo
    for key, header in (("support_url", "support-url"),
                        ("web_page_url", "profile-web-page-url")):
        url = _safe_url(items.get(header))
        if url:
            provider[key] = url
    announce = _clean_text(items.get("announce"), MAX_ANNOUNCE_CHARS)
    if announce:
        provider["announce"] = announce
    return provider


def parse_body_metadata(text):
    """The `#profile-title:` / `#subscription-userinfo:` lines -> provider dict.

    Only the first 256 lines are inspected: these lines belong at the top of a
    body, and a multi-megabyte link list should not be scanned end to end for
    metadata that cannot be there.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    provider = {}
    for line in str(text or "").splitlines()[:256]:
        match = _METADATA_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        if key == "profile-title" and "title" not in provider:
            title = decode_profile_title(value)
            if title:
                provider["title"] = title
        elif key == "profile-update-interval" and "update_interval_hours" not in provider:
            interval = _interval(value)
            if interval:
                provider["update_interval_hours"] = interval
        elif key == "subscription-userinfo" and "userinfo" not in provider:
            userinfo = parse_userinfo(value)
            if userinfo:
                provider["userinfo"] = userinfo
        elif key == "support-url" and "support_url" not in provider:
            url = _safe_url(value)
            if url:
                provider["support_url"] = url
        elif key == "profile-web-page-url" and "web_page_url" not in provider:
            url = _safe_url(value)
            if url:
                provider["web_page_url"] = url
        elif key == "announce" and "announce" not in provider:
            announce = _clean_text(value, MAX_ANNOUNCE_CHARS)
            if announce:
                provider["announce"] = announce
    return provider


def sanitize_provider(value):
    """A stored provider dict with every field in range; `{}` for junk."""
    if not isinstance(value, dict):
        return {}
    out = {}
    title = _clean_text(value.get("title"), MAX_TITLE_CHARS)
    if title:
        out["title"] = title
    interval = _clamp_int(value.get("update_interval_hours"), MIN_INTERVAL_HOURS,
                          MAX_INTERVAL_HOURS)
    if interval:
        out["update_interval_hours"] = interval
    userinfo = value.get("userinfo")
    if isinstance(userinfo, dict):
        clean = {}
        for key in ("upload", "download", "total", "expire"):
            number = _clamp_int(userinfo.get(key), 0, MAX_BYTES)
            if number is not None:
                clean[key] = number
        if "expire" in clean and clean["expire"] > 1_000_000_000_000:
            clean["expire"] //= 1000
        if clean:
            out["userinfo"] = clean
    for key in ("support_url", "web_page_url"):
        url = _safe_url(value.get(key))
        if url:
            out[key] = url
    announce = _clean_text(value.get("announce"), MAX_ANNOUNCE_CHARS)
    if announce:
        out["announce"] = announce
    updated = _clamp_int(value.get("updated_at"), 0, MAX_BYTES)
    if updated:
        out["updated_at"] = updated
    return out


def merge_provider(old, new, now=None):
    """Keep what is already known and overlay the fields this answer carried.

    A refresh that answers 304 or omits `Support-Url` must not erase the title
    and traffic numbers learned earlier; only an explicit new value replaces.
    """
    current = sanitize_provider(old)
    fresh = sanitize_provider(new)
    if not fresh:
        return current
    merged = dict(current)
    for key in ("title", "update_interval_hours", "support_url", "web_page_url", "announce"):
        if key in fresh:
            merged[key] = fresh[key]
    if "userinfo" in fresh:
        userinfo = dict(current.get("userinfo") or {})
        userinfo.update(fresh["userinfo"])
        merged["userinfo"] = userinfo
    stamp = _clamp_int(now, 0, MAX_BYTES)
    if stamp:
        merged["updated_at"] = stamp
    elif "updated_at" in fresh:
        merged["updated_at"] = fresh["updated_at"]
    return merged
