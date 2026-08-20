from collections import defaultdict
from math import ceil
from time import monotonic
from fastapi import HTTPException

_key_ops: dict[str, list[float]] = defaultdict(list)
_MAX_KEY_OPS = 5
_KEY_WINDOW = 60.0  # seconds


def key_rate_limit_status(user_id: str) -> dict[str, int]:
    now = monotonic()
    _key_ops[user_id] = [t for t in _key_ops[user_id] if now - t < _KEY_WINDOW]
    used = len(_key_ops[user_id])
    retry_after = ceil(_KEY_WINDOW - (now - _key_ops[user_id][0])) if used >= _MAX_KEY_OPS else 0
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
    _key_ops[user_id].append(monotonic())
