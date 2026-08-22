from collections import defaultdict
from math import ceil
from threading import Lock
from time import monotonic
from fastapi import HTTPException

_key_ops: dict[str, list[float]] = defaultdict(list)
_login_failures: dict[str, list[float]] = defaultdict(list)
_MAX_KEY_OPS = 5
_KEY_WINDOW = 60.0  # seconds
_MAX_LOGIN_FAILURES = 8
_LOGIN_WINDOW = 300.0
_lock = Lock()


def _prune(events: dict[str, list[float]], identity: str, window: float, now: float) -> list[float]:
    current = [timestamp for timestamp in events.get(identity, []) if now - timestamp < window]
    if current:
        events[identity] = current
    else:
        events.pop(identity, None)
    return current


def key_rate_limit_status(user_id: str) -> dict[str, int]:
    now = monotonic()
    with _lock:
        current = _prune(_key_ops, user_id, _KEY_WINDOW, now)
    used = len(current)
    retry_after = ceil(_KEY_WINDOW - (now - current[0])) if used >= _MAX_KEY_OPS else 0
    return {
        "limit": _MAX_KEY_OPS,
        "remaining": max(0, _MAX_KEY_OPS - used),
        "retry_after": max(0, retry_after),
    }


def check_key_rate_limit(user_id: str) -> None:
    status = key_rate_limit_status(user_id)
    if status["remaining"] == 0:
        raise HTTPException(
            status_code=429,
            detail=f"Too many operations. Try again in {status['retry_after']} seconds.",
            headers={"Retry-After": str(status["retry_after"])},
        )
    with _lock:
        _key_ops[user_id].append(monotonic())


def check_login_rate_limit(client_id: str) -> None:
    """Block password attempts after repeated failures from one client."""
    now = monotonic()
    with _lock:
        failures = _prune(_login_failures, client_id, _LOGIN_WINDOW, now)
    if len(failures) >= _MAX_LOGIN_FAILURES:
        retry_after = max(1, ceil(_LOGIN_WINDOW - (now - failures[0])))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed sign-in attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def record_login_failure(client_id: str) -> None:
    with _lock:
        _login_failures[client_id].append(monotonic())


def clear_login_failures(client_id: str) -> None:
    with _lock:
        _login_failures.pop(client_id, None)
