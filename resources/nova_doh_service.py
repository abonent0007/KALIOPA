"""Локальный DoH-резолвер как служба Nova: старт, стоп, восстановление DNS.

Схема: снимок DNS адаптеров -> файл-страховка -> резолвер на 127.0.0.1:53 ->
адаптеры переключаются на 127.0.0.1. При остановке адаптеры возвращаются к
снимку, файл удаляется. Если прошлый запуск упал, `recover` вернёт адреса до
того, как пользователь что-то заметит.

По умолчанию выключено: включение — `NOVA_DOH_GLOBAL=1`. Причина — резолвер
на порту 53 перекрывает системный DNS целиком; NRPT-путь Nova остаётся
основным, а этот режим нужен там, где NRPT не поддержан.
"""

import os
import threading

import nova_dns_adapters
import nova_doh_resolver

DOH_LISTEN_IP = "127.0.0.1"
DOH_LISTEN_PORT = 53

_lock = threading.Lock()
_resolver = None


def enabled():
    raw = os.environ.get("NOVA_DOH_GLOBAL")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def snapshot_path(temp_dir):
    return os.path.join(str(temp_dir), nova_dns_adapters.SNAPSHOT_FILENAME)


def _fallback_upstream(rows):
    """Первый прежний DNS-сервер: если DoH молчит, резолвер не оставит сеть без DNS."""
    for row in rows or []:
        for server in row.get("servers") or []:
            server = str(server or "").strip()
            if server and server != DOH_LISTEN_IP:
                return "%s:53" % server
    return None


def start(temp_dir, log=None, *, adapters=None, resolver_factory=None):
    """Поднять резолвер и перевести адаптеры. Возвращает True при успехе."""
    global _resolver
    say = log if callable(log) else (lambda _text: None)
    with _lock:
        if _resolver is not None:
            return True
        adapters = adapters or nova_dns_adapters
        path = snapshot_path(temp_dir)
        try:
            rows = adapters.snapshot()
            if not rows:
                say("[DoH] адаптеры с DNS не найдены — режим не включён")
                return False
            adapters.save(path, rows)
        except Exception as exc:
            say("[DoH] снимок DNS не сделан: %s" % exc)
            return False
        factory = resolver_factory or nova_doh_resolver.DohResolver
        resolver = factory(upstream=_fallback_upstream(rows))
        try:
            resolver.start()
            adapters.apply(rows, DOH_LISTEN_IP)
        except Exception as exc:
            try:
                adapters.restore(rows)
            except Exception:
                pass
            try:
                resolver.stop()
            except Exception:
                pass
            try:
                os.remove(path)
            except OSError:
                pass
            say("[DoH] запуск не удался, DNS возвращён: %s" % exc)
            return False
        _resolver = resolver
        say("[DoH] локальный резолвер поднят на %s:%d, адаптеры переведены; "
            "возврат к снимку при выходе." % (DOH_LISTEN_IP, DOH_LISTEN_PORT))
        return True


def stop(temp_dir=None, log=None, *, adapters=None):
    """Остановить резолвер и вернуть DNS. Безопасно вызывать повторно."""
    global _resolver
    say = log if callable(log) else (lambda _text: None)
    with _lock:
        resolver, _resolver = _resolver, None
        if resolver is not None:
            try:
                resolver.stop()
            except Exception:
                pass
        if not temp_dir:
            return
        adapters = adapters or nova_dns_adapters
        try:
            if adapters.recover(temp_dir):
                say("[DoH] DNS адаптеров возвращён к снимку.")
        except Exception as exc:
            say("[DoH] DNS не восстановлен: %s" % exc)


def recover(temp_dir, log=None, *, adapters=None):
    """Восстановление после падения прошлого запуска; вызывается на старте."""
    say = log if callable(log) else (lambda _text: None)
    adapters = adapters or nova_dns_adapters
    try:
        if adapters.recover(temp_dir):
            say("[DoH] найден снимок прошлого запуска — DNS адаптеров восстановлен.")
            return True
    except Exception as exc:
        say("[DoH] снимок прошлого запуска не применён: %s" % exc)
    return False
