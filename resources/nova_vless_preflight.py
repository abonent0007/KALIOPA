"""Предварительная проба VLESS-узлов перед тем, как они займут место в подписке.

Мёртвый endpoint — это 12 секунд ожидания при каждом подключении и запись в
карантин после трёх попыток. Дешевле отсеять его на импорте: TCP-коннект к
`host:port` с таймаутом 2 с, параллельно по 8 узлов.

TLS-рукопожатие по умолчанию выключено (`NOVA_VLESS_PREFLIGHT_TLS=1` включает).
Причина: проба идёт напрямую, мимо туннеля, а SNI узла может быть заблокирован
DPI именно на этом пути — рабочий через WARP узел выглядел бы мёртвым. TCP же
отвечает независимо от SNI, поэтому отсеивает настоящие трупы, не трогая живые.
"""

import concurrent.futures
import os
import socket
import ssl

DEFAULT_TIMEOUT = 2.0
DEFAULT_WORKERS = 8

__all__ = ["enabled", "tls_enabled", "probe_node", "probe_nodes"]


def enabled():
    """`NOVA_VLESS_PREFLIGHT=0` выключает пробу целиком."""
    raw = os.environ.get("NOVA_VLESS_PREFLIGHT")
    if raw is None:
        return True
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def tls_enabled():
    raw = os.environ.get("NOVA_VLESS_PREFLIGHT_TLS")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _target(node):
    host = str(getattr(node, "host", "") or "").strip()
    try:
        port = int(getattr(node, "port", 0) or 0)
    except (TypeError, ValueError):
        port = 0
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host, port


def _tls_server_name(node, host):
    name = str(getattr(node, "sni", "") or getattr(node, "host_header", "") or host).strip()
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    return name or host


def probe_node(node, timeout=DEFAULT_TIMEOUT, tls=None):
    """Пустая строка — endpoint ответил; иначе короткая причина отказа."""
    host, port = _target(node)
    if not host or port <= 0:
        return "нет адреса или порта"
    try:
        sock = socket.create_connection((host, port), timeout=max(0.2, float(timeout)))
    except OSError as exc:
        reason = getattr(exc, "strerror", None) or type(exc).__name__
        return "нет TCP: %s" % reason
    use_tls = tls_enabled() if tls is None else bool(tls)
    if not use_tls:
        sock.close()
        return ""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_alpn_protocols(["h2", "http/1.1"])
    try:
        with context.wrap_socket(sock, server_hostname=_tls_server_name(node, host)):
            return ""
    except (ssl.SSLError, OSError) as exc:
        reason = getattr(exc, "reason", None) or getattr(exc, "strerror", None) or type(exc).__name__
        return "нет TLS: %s" % reason
    finally:
        try:
            sock.close()
        except OSError:
            pass


def probe_nodes(nodes, timeout=DEFAULT_TIMEOUT, workers=DEFAULT_WORKERS, prober=None):
    """(живые, [(узел, причина)]). `prober` подменяется в тестах."""
    items = [node for node in (nodes or []) if node is not None]
    if not items:
        return [], []
    probe = prober or probe_node
    alive = []
    rejected = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(workers or 1))) as pool:
        futures = {pool.submit(probe, node, timeout): node for node in items}
        for future in concurrent.futures.as_completed(futures):
            node = futures[future]
            try:
                reason = future.result()
            except Exception as exc:  # проба не должна ронять обновление подписки
                reason = type(exc).__name__
            if reason:
                rejected.append((node, str(reason)))
            else:
                alive.append(node)
    return alive, rejected
