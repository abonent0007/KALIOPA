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
import socket
import subprocess
import sys
import threading

import nova_dns_adapters

DOH_LISTEN_IP = "127.0.0.1"
try:
    DOH_LISTEN_PORT = max(1, min(65535, int(os.environ.get("NOVA_DOH_PORT", "53") or 53)))
except ValueError:
    DOH_LISTEN_PORT = 53

DOH_URL = "https://dns.dns-ai.ru/dns-query"

_lock = threading.Lock()
_resolver = None


def _nova_go_path():
    """nova-go.exe рядом с приложением: resources\\bin (сборка) или bin (исходники)."""
    base = os.path.dirname(os.path.abspath(sys.argv[0] or "."))
    for rel in (("resources", "bin", "nova-go.exe"), ("bin", "nova-go.exe")):
        path = os.path.join(base, *rel)
        if os.path.exists(path):
            return path
    return ""


class _GoResolver:
    """DoH-резолвер на `nova-go dns doh`: HTTP/2 даёт Go, зависимости httpx/h2 не нужны."""

    def __init__(self, port=DOH_LISTEN_PORT, upstream=None, proxy=None):
        self.port = int(port)
        self.upstream = upstream or ""
        self.proxy = proxy or ""
        self._process = None
        self._log = None

    def start(self):
        helper = _nova_go_path()
        if not helper:
            raise RuntimeError("nova-go.exe не найден")
        args = [helper, "dns", "doh",
                "--listen", f"{DOH_LISTEN_IP}:{self.port}",
                "--upstream", DOH_URL,
                "--timeout", "5s",
                "--parent-pid", str(os.getpid())]
        if self.upstream:
            args += ["--fallback", self.upstream]
        if self.proxy:
            args += ["--proxy", self.proxy]
        self._log = open(os.devnull, "wb")
        self._process = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=self._log, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        if self._process.poll() is not None:
            raise RuntimeError("nova-go dns doh сразу завершился")

    def stop(self):
        proc, self._process = self._process, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._log is not None:
            try:
                self._log.close()
            except Exception:
                pass
            self._log = None


def enabled():
    raw = os.environ.get("NOVA_DOH_GLOBAL")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def snapshot_path(temp_dir):
    return os.path.join(str(temp_dir), nova_dns_adapters.SNAPSHOT_FILENAME)


def _proxy_url():
    """Живой слот Nova: WARP SOCKS 1370, затем Opera HTTP 1371. Без них DoH рвётся DPI."""
    for port, scheme in ((1370, "socks5"), (1371, "http")):
        try:
            with socket.create_connection((DOH_LISTEN_IP, port), timeout=0.3):
                return f"{scheme}://{DOH_LISTEN_IP}:{port}"
        except OSError:
            continue
    return ""


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
        factory = resolver_factory
        if factory is None:
            use_python = str(os.environ.get("NOVA_DOH_PY", "")).strip().lower() in {"1", "true", "yes", "on"}
            if use_python:
                # Старый путь на httpx остаётся для отладки: ему нужен пакет h2,
                # которого нет в сборочном Python 3.14.
                import nova_doh_resolver
                factory = nova_doh_resolver.DohResolver
            else:
                factory = _GoResolver
        resolver = factory(upstream=_fallback_upstream(rows))
        if isinstance(resolver, _GoResolver) and not resolver.proxy:
            resolver.proxy = _proxy_url()
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
        resolver = _resolver
        _resolver = None
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
