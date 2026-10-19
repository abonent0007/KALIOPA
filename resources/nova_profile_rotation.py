"""Automatic node rotation inside the selected profile group.

The policy is pure: it has no sockets, threads or project imports. The monitor and
the adapters at the bottom are the only parts that touch Nova's profile store and
the local SOCKS5 port.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

ROTATABLE_GROUPS = frozenset({"AWG Proton", "VLESS", "Custom"})
ROTATABLE_IN_AUTO = frozenset({"AWG Proton"})

SAMPLE_INTERVAL_SEC = 45.0
MIN_ACTIVE_SEC = 90.0
MIN_BASELINE_SAMPLES = 3
DEGRADED_SAMPLES = 3
COOLDOWN_SEC = 15 * 60.0
MAX_ROTATIONS_PER_HOUR = 2
EWMA_ALPHA = 0.3
RTT_DEGRADED_FACTOR = 1.8
MIN_RTT_MS = 30.0
RTT_IMPROVEMENT_FACTOR = 0.70
RTT_IMPROVEMENT_FACTOR_FAILING = 0.85
CANDIDATE_PROBE_COOLDOWN_SEC = 5 * 60.0
LOG_HOLD_COOLDOWN_SEC = 10 * 60.0
FAILED_ROTATION_RETRY_SEC = 60.0
USER_ACTION_COOLDOWN_SEC = 5 * 60.0

CANARY_TARGETS = (
    ("www.cloudflare.com", "/cdn-cgi/trace"),
    ("1.1.1.1", "/cdn-cgi/trace"),
    ("www.google.com", "/robots.txt"),
)


@dataclass(frozen=True)
class ProfileCandidate:
    profile_id: str
    group: str
    rtt_ms: float | None = None
    last_ok_at: float = 0.0
    last_fail_at: float = 0.0
    fail_streak: int = 0


@dataclass(frozen=True)
class RotationDecision:
    rotate: bool
    profile_id: str = ""
    reason: str = ""


def choose_candidate(current_id, current_group, current_rtt_ms, candidates, *, failing=False):
    """Fastest healthy node of the same group, at least 30% better by direct RTT."""
    factor = RTT_IMPROVEMENT_FACTOR_FAILING if failing else RTT_IMPROVEMENT_FACTOR
    usable = []
    for candidate in candidates or ():
        if not isinstance(candidate, ProfileCandidate):
            continue
        if candidate.profile_id == current_id or candidate.group != current_group:
            continue
        if candidate.rtt_ms is None or candidate.rtt_ms <= 0:
            continue
        if candidate.fail_streak > 0:
            continue
        if candidate.last_fail_at > candidate.last_ok_at:
            continue
        usable.append(candidate)
    if not usable:
        return None
    usable.sort(key=lambda item: (float(item.rtt_ms), -float(item.last_ok_at), item.profile_id))
    best = usable[0]
    if current_rtt_ms is None or current_rtt_ms <= 0:
        return best
    if float(best.rtt_ms) <= float(current_rtt_ms) * factor:
        return best
    return None


class RotationPolicy:
    """Hysteresis, cooldown and candidate choice; all times are caller-supplied."""

    def __init__(self, enabled=True):
        self.enabled = bool(enabled)
        self.active_since = 0.0
        self.baseline_ms = None
        self.samples = 0
        self.degraded_streak = 0
        self.last_rotation_at = 0.0
        self.rotation_times = deque()
        self.last_candidate_probe_at = 0.0
        self.last_hold_log_at = 0.0
        self.last_user_action_at = 0.0
        self.active_id = ""

    def reset(self, now, active_id=""):
        self.active_since = float(now)
        self.baseline_ms = None
        self.samples = 0
        self.degraded_streak = 0
        self.active_id = str(active_id or "")

    def observe(self, now, canary_ms, canary_ok, fail_streak=0):
        """Feed one health sample; True when the channel has been degraded long enough."""
        if not self.enabled:
            return False
        if canary_ok is None:
            return self.degraded_streak >= DEGRADED_SAMPLES
        if float(now) - self.active_since < MIN_ACTIVE_SEC:
            return False
        if canary_ok and canary_ms is not None:
            value = float(canary_ms)
            if self.baseline_ms is None:
                self.baseline_ms = value
                self.samples = 1
                self.degraded_streak = 0
                return False
            self.samples += 1
            threshold = max(MIN_RTT_MS, float(self.baseline_ms) * RTT_DEGRADED_FACTOR)
            if value > threshold or int(fail_streak or 0) > 0:
                self.degraded_streak += 1
            else:
                self.degraded_streak = 0
                self.baseline_ms = EWMA_ALPHA * value + (1.0 - EWMA_ALPHA) * float(self.baseline_ms)
        else:
            self.degraded_streak += 1
        return self.degraded_streak >= DEGRADED_SAMPLES

    def can_rotate(self, now, mode, group):
        if not self.enabled:
            return False
        if str(mode or "") == "profile":
            return False
        if str(group or "") not in ROTATABLE_GROUPS:
            return False
        if str(mode or "") == "auto" and str(group or "") not in ROTATABLE_IN_AUTO:
            return False
        now = float(now)
        if now - self.active_since < MIN_ACTIVE_SEC:
            return False
        if self.last_rotation_at and now - self.last_rotation_at < COOLDOWN_SEC:
            return False
        if self.last_user_action_at and now - self.last_user_action_at < USER_ACTION_COOLDOWN_SEC:
            return False
        cutoff = now - 3600.0
        while self.rotation_times and self.rotation_times[0] < cutoff:
            self.rotation_times.popleft()
        return len(self.rotation_times) < MAX_ROTATIONS_PER_HOUR

    def can_probe_candidates(self, now):
        return float(now) - self.last_candidate_probe_at >= CANDIDATE_PROBE_COOLDOWN_SEC

    def note_candidate_probe(self, now):
        self.last_candidate_probe_at = float(now)

    def note_user_action(self, now):
        self.last_user_action_at = float(now)
        self.degraded_streak = 0
        self.baseline_ms = None
        self.samples = 0

    def decide(self, now, *, mode, current_id, current_group, current_direct_ms, candidates,
               failing=False):
        if self.degraded_streak < DEGRADED_SAMPLES:
            return RotationDecision(False, reason="недостаточно сэмплов")
        if not self.can_rotate(now, mode, current_group):
            return RotationDecision(False, reason="cooldown или режим")
        candidate = choose_candidate(
            current_id, current_group, current_direct_ms, candidates, failing=failing
        )
        if candidate is None:
            return RotationDecision(False, reason="нет узла быстрее")
        if current_direct_ms and float(current_direct_ms) > 0:
            gain = int(round((1.0 - float(candidate.rtt_ms) / float(current_direct_ms)) * 100))
            reason = f"узел {candidate.profile_id} быстрее на {max(1, gain)}%"
        else:
            reason = f"узел {candidate.profile_id} отвечает быстрее"
        return RotationDecision(True, candidate.profile_id, reason)

    def note_rotation(self, now, success):
        now = float(now)
        if success:
            self.last_rotation_at = now
            self.rotation_times.append(now)
            self.active_since = now
            self.baseline_ms = None
            self.samples = 0
            self.degraded_streak = 0
        else:
            self.last_rotation_at = now - COOLDOWN_SEC + FAILED_ROTATION_RETRY_SEC
            self.degraded_streak = 0

    def should_log_hold(self, now):
        now = float(now)
        if self.last_hold_log_at and now - self.last_hold_log_at < LOG_HOLD_COOLDOWN_SEC:
            return False
        self.last_hold_log_at = now
        return True


def find_profile(base_dir, profile_id):
    import nova_profiles

    profile_id = str(profile_id or "").strip()
    if not profile_id:
        return None
    try:
        records = nova_profiles.list_profiles(base_dir)
    except Exception:
        return None
    for record in records:
        if isinstance(record, dict) and str(record.get("id") or "") == profile_id:
            return record
    return None


def _endpoint_parts(endpoint):
    text = str(endpoint or "").strip()
    if not text:
        return "", 0
    if text.startswith("["):
        host, sep, tail = text[1:].partition("]")
        port_text = tail.lstrip(":") if sep else ""
    else:
        host, sep, port_text = text.rpartition(":")
        if not sep:
            host, port_text = text, ""
    try:
        port = int(port_text)
    except (TypeError, ValueError):
        port = 0
    return host.strip(), port if 0 < port < 65536 else 0


def _rtt_target(record):
    import nova_latency
    import nova_profiles

    host, port = _endpoint_parts(record.get("endpoint"))
    if not host:
        return None
    if record.get("kind") == getattr(nova_profiles, "KIND_VLESS", "vless") and port:
        return host, port
    return host, 443


def _fresh_rtt(stats, profile_id, now, max_age=600.0):
    entry = stats.get(str(profile_id or "")) if isinstance(stats, dict) else None
    entry = entry if isinstance(entry, dict) else {}
    try:
        measured_at = float(entry.get("rtt_at") or 0.0)
        value = entry.get("rtt_ms")
        if value is not None and measured_at and 0 <= float(now) - measured_at < float(max_age):
            return float(value)
    except (TypeError, ValueError):
        pass
    return None


def load_candidates(base_dir, group, current_id, now=None, limit=12):
    """Profiles of the same group, with a fresh direct RTT where possible."""
    import nova_latency
    import nova_profiles

    now = time.time() if now is None else float(now)
    try:
        records = nova_profiles.list_profiles(base_dir)
        stats = nova_profiles.load_stats(base_dir)
        selection = nova_profiles.load_selection(base_dir)
    except Exception:
        return []
    country = ""
    if group == getattr(nova_profiles, "GROUP_PROTON", "AWG Proton"):
        country = str(selection.get("country") or "").strip().upper()

    picked = []
    for record in records:
        if not isinstance(record, dict) or not record.get("valid"):
            continue
        if record.get("group") != group:
            continue
        profile_id = str(record.get("id") or "")
        if not profile_id or profile_id == str(current_id or ""):
            continue
        if country:
            try:
                if str(nova_profiles.record_country(record) or "").upper() != country:
                    continue
            except Exception:
                continue
        picked.append(record)
    def _rank(record):
        profile_id = str(record.get("id") or "")
        entry = stats.get(profile_id) if isinstance(stats, dict) else None
        entry = entry if isinstance(entry, dict) else {}
        rtt = _fresh_rtt(stats, profile_id, now)
        try:
            last_ok = float(entry.get("last_ok_at") or 0.0)
        except (TypeError, ValueError):
            last_ok = 0.0
        return (rtt is None, float(rtt or 0.0), -last_ok, profile_id)

    picked.sort(key=_rank)
    picked = picked[:max(1, int(limit))]

    targets = {}
    entries = {}
    for record in picked:
        profile_id = str(record.get("id") or "")
        entry = stats.get(profile_id) if isinstance(stats, dict) else None
        entry = entry if isinstance(entry, dict) else {}
        entries[profile_id] = entry
        if _fresh_rtt(stats, profile_id, now) is None:
            target = _rtt_target(record)
            if target is not None:
                targets[profile_id] = target[0]
    measured = {}
    if targets:
        try:
            measured = nova_latency.measure_tcp_rtts(targets, timeout=1.5, max_workers=8)
            nova_profiles.record_rtts(base_dir, measured)
        except Exception:
            measured = {}
    candidates = []
    for record in picked:
        profile_id = str(record.get("id") or "")
        entry = entries.get(profile_id) or {}
        rtt = _fresh_rtt(stats, profile_id, now)
        raw_rtt = measured.get(profile_id)
        if rtt is None and raw_rtt is not None:
            try:
                rtt = float(raw_rtt)
            except (TypeError, ValueError):
                rtt = None
        if rtt is None:
            continue
        try:
            last_ok = float(entry.get("last_ok_at") or 0.0)
            last_fail = float(entry.get("last_fail_at") or 0.0)
            fail_streak = int(entry.get("fail_streak") or 0)
        except (TypeError, ValueError):
            last_ok, last_fail, fail_streak = 0.0, 0.0, 0
        candidates.append(ProfileCandidate(profile_id, group, rtt, last_ok, last_fail, fail_streak))
    return candidates


def measure_direct(base_dir, profile_id, now=None):
    import nova_latency
    import nova_profiles

    now = time.time() if now is None else float(now)
    try:
        stats = nova_profiles.load_stats(base_dir)
    except Exception:
        stats = {}
    rtt = _fresh_rtt(stats, profile_id, now)
    if rtt is not None:
        return rtt
    record = find_profile(base_dir, profile_id)
    if not record:
        return None
    target = _rtt_target(record)
    if target is None:
        return None
    try:
        value = nova_latency.measure_tcp_rtt(target[0], target[1], timeout=1.5)
        if value is not None:
            nova_profiles.record_rtts(base_dir, {profile_id: value})
        return float(value) if value is not None else None
    except Exception:
        return None


def probe_canary(port, budget=4.0):
    """One tiny HTTP probe through the active SOCKS5; returns (ms, ok or None)."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1.0):
            pass
    except OSError:
        return None, None

    import nova_exit_probe

    for host, path in CANARY_TARGETS:
        started = time.perf_counter()
        try:
            nova_exit_probe.fetch_via_proxy(
                "socks5", int(port), host, path, budget=float(budget)
            )
            return (time.perf_counter() - started) * 1000.0, True
        except Exception:
            continue
    return None, False


class ProfileRotationMonitor:
    """Background monitor; all decisions live in RotationPolicy."""

    def __init__(self, *, get_state, rotate, log, stop, base_dir,
                 interval=SAMPLE_INTERVAL_SEC, enabled=True,
                 candidates_loader=load_candidates, canary_probe=probe_canary,
                 direct_probe=measure_direct):
        self._get_state = get_state
        self._rotate = rotate
        self._log = log or (lambda message: None)
        self._stop = stop or (lambda: False)
        self._base_dir = base_dir
        self._interval = max(10.0, float(interval))
        self._enabled = bool(enabled)
        self._candidates_loader = candidates_loader
        self._canary_probe = canary_probe
        self._direct_probe = direct_probe
        self._policy = RotationPolicy(enabled=enabled)
        self._active_id = ""
        self._thread = None

    def start(self):
        if not self._enabled or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True, name="NovaProfileRotation")
        self._thread.start()
        return True

    def note_user_action(self, now=None):
        self._policy.note_user_action(time.monotonic() if now is None else now)

    def _run(self):
        while not self._stop():
            time.sleep(self._interval)
            if self._stop():
                return
            try:
                self._tick()
            except Exception as exc:
                self._log(f"[Profiles] Ротация: {type(exc).__name__}: {exc}")

    def _tick(self):
        state = self._get_state() or {}
        if not state.get("connected") or state.get("starting") or state.get("recovering"):
            self._policy.reset(time.monotonic(), self._active_id)
            return
        active_id = str(state.get("active_id") or "")
        group = str(state.get("group") or "")
        mode = str(state.get("mode") or "auto")
        try:
            port = int(state.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if not active_id or port <= 0:
            return
        if mode == "profile" or group not in ROTATABLE_GROUPS:
            return
        if mode == "auto" and group not in ROTATABLE_IN_AUTO:
            return

        now = time.monotonic()
        if active_id != self._active_id:
            self._policy.reset(now, active_id)
            self._active_id = active_id
        canary_ms, canary_ok = self._canary_probe(port)
        if canary_ok is None:
            return
        fail_streak = int(state.get("fail_streak") or 0)
        if not self._policy.observe(now, canary_ms, canary_ok, fail_streak):
            return
        if not self._policy.can_rotate(now, mode, group):
            return
        if not self._policy.can_probe_candidates(now):
            return
        current_direct = self._direct_probe(self._base_dir, active_id, time.time())
        candidates = self._candidates_loader(self._base_dir, group, active_id, time.time())
        self._policy.note_candidate_probe(now)
        decision = self._policy.decide(
            now,
            mode=mode,
            current_id=active_id,
            current_group=group,
            current_direct_ms=current_direct,
            candidates=candidates,
            failing=fail_streak > 0,
        )
        if not decision.rotate:
            if self._policy.should_log_hold(now):
                self._log(f"[Profiles] Деградация канала: {decision.reason}; остаёмся на {active_id}.")
            return
        latest = self._get_state() or {}
        if str(latest.get("active_id") or "") != active_id:
            return
        if latest.get("starting") or latest.get("recovering"):
            return
        ok = bool(self._rotate(decision.profile_id, decision.reason))
        self._policy.note_rotation(now, ok)
        prefix = "[Profiles] Ротация" if ok else "[Profiles] Ротация не удалась"
        self._log(f"{prefix}: {active_id} -> {decision.profile_id} ({decision.reason}).")
