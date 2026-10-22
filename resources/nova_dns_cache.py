"""TTL-aware DNS result cache with explicit negative entries."""

from __future__ import annotations

import socket

DEFAULT_TTL_SEC = 300
DEFAULT_NEGATIVE_TTL_SEC = 60


def choose_ip(addresses):
    """IPv4 first, then the first IPv6 from `(family, ip)` pairs or plain strings."""
    ipv6 = None
    for item in addresses or ():
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            value = str(item[1] or "").strip()
        else:
            value = str(item or "").strip()
        if not value:
            continue
        if ":" not in value:
            return value
        if ipv6 is None:
            ipv6 = value
    return ipv6


class DNSCache:
    def __init__(self, data=None, ttl=DEFAULT_TTL_SEC, negative_ttl=DEFAULT_NEGATIVE_TTL_SEC):
        self.data = data if isinstance(data, dict) else {}
        self.ttl = max(1, int(ttl))
        self.negative_ttl = max(1, int(negative_ttl))

    def _expires_at(self, entry):
        value = entry.get("expires_at") if isinstance(entry, dict) else None
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass
        try:
            timestamp = float((entry or {}).get("timestamp") or 0.0)
        except (TypeError, ValueError):
            timestamp = 0.0
        ttl = self.negative_ttl if (entry or {}).get("ip") is None else self.ttl
        return timestamp + ttl

    def get(self, domain, now):
        entry = self.data.get(str(domain or "").lower())
        if not isinstance(entry, dict):
            return None
        if float(now) >= self._expires_at(entry):
            return None
        ip = entry.get("ip")
        return (ip, "cached_ok" if ip else "cached_no_dns")

    def put(self, domain, ip, now, ttl=None):
        if ip is None:
            lifetime = self.negative_ttl if ttl is None else max(1, int(ttl))
        else:
            lifetime = self.ttl if ttl is None else max(1, int(ttl))
        self.data[str(domain or "").lower()] = {
            "ip": ip,
            "timestamp": float(now),
            "expires_at": float(now) + lifetime,
        }

    def resolve(self, domain, resolver, now, use_cache=True):
        domain = str(domain or "").lower()
        if use_cache:
            cached = self.get(domain, now)
            if cached is not None:
                return cached
        try:
            addresses = resolver(domain)
        except socket.gaierror:
            self.put(domain, None, now)
            return None, "no_dns"
        except Exception:
            self.put(domain, None, now)
            return None, "error"
        ip = choose_ip(addresses)
        if not ip:
            self.put(domain, None, now)
            return None, "no_dns"
        self.put(domain, ip, now)
        return ip, "ok"
