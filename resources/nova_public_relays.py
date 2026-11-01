import os
from dataclasses import dataclass

from nova_routing_backends import is_public_hybrid_backend


@dataclass(frozen=True)
class PublicRelaySpec:
    key: str
    display_name: str
    tcp_backend: str
    component_key: str
    host: str
    port: int
    enabled: bool
    implementation: str
    planned_only: bool = False


def get_public_relay_specs(backend_mode):
    public_hybrid = is_public_hybrid_backend(backend_mode)
    telegram_relay_enabled = str(os.environ.get("NOVA_TELEGRAM_RELAY", "1") or "").strip().lower()
    telegram_relay_enabled = telegram_relay_enabled not in {"0", "false", "off", "no"}
    return {
        "telegram": PublicRelaySpec(
            key="telegram",
            display_name="Telegram relay",
            tcp_backend="telegram-relay",
            component_key="telegram_relay_ready",
            host="127.0.0.1",
            port=1372,
            enabled=telegram_relay_enabled or public_hybrid,
            implementation="tgrelay",
            planned_only=False,
        ),
        "whatsapp": PublicRelaySpec(
            key="whatsapp",
            display_name="WhatsApp relay",
            tcp_backend="whatsapp-relay",
            component_key="whatsapp_relay_ready",
            host="127.0.0.1",
            port=1377,
            enabled=False,
            implementation="planned",
            planned_only=True,
        ),
    }


def get_enabled_public_relay_specs(backend_mode):
    specs = get_public_relay_specs(backend_mode)
    return {key: spec for key, spec in specs.items() if bool(spec.enabled)}


def _safe_call(func, default):
    """Значение из чужого объекта или fallback: снимок не должен падать."""
    try:
        return func()
    except Exception:
        return default


def build_public_relay_snapshot(backend_mode, managers):
    specs = get_public_relay_specs(backend_mode)
    managers = managers or {}
    snapshot = {}
    for key, spec in specs.items():
        manager = managers.get(key)
        ready = bool(manager) and bool(
            _safe_call(lambda: getattr(manager, "is_ready", lambda: False)(), False)
        )
        running = bool(manager) and bool(
            _safe_call(lambda: getattr(getattr(manager, "server", None), "running", False), False)
        )
        if ready:
            running = True
        bind_port = int(spec.port)
        if manager:
            bind_port = _safe_call(
                lambda: int(getattr(manager, "port", spec.port) or spec.port), int(spec.port)
            )
        snapshot[key] = {
            "key": spec.key,
            "display_name": spec.display_name,
            "tcp_backend": spec.tcp_backend,
            "component_key": spec.component_key,
            "enabled": bool(spec.enabled),
            "ready": bool(ready),
            "running": bool(running),
            "implementation": spec.implementation,
            "planned_only": bool(spec.planned_only),
            "bind": f"{spec.host}:{bind_port}",
        }
    return snapshot
