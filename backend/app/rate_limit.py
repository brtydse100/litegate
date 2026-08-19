from collections import defaultdict
from time import monotonic
from fastapi import HTTPException

_key_ops: dict[str, list[float]] = defaultdict(list)
_MAX_KEY_OPS = 5
_KEY_WINDOW = 60.0  # seconds


def check_key_rate_limit(user_id: str) -> None:
    now = monotonic()
    _key_ops[user_id] = [t for t in _key_ops[user_id] if now - t < _KEY_WINDOW]
    if len(_key_ops[user_id]) >= _MAX_KEY_OPS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many key operations. Try again in {_KEY_WINDOW:.0f} seconds.",
        )
    _key_ops[user_id].append(now)
