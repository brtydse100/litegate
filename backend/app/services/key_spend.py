"""Read current key counters without trusting cached user-list metadata."""

import asyncio
import math
from datetime import datetime, timezone
from fastapi import HTTPException
from app.services import litellm


def counter(info: dict) -> float:
    value = info.get("spend")
    if isinstance(value, bool):
        raise HTTPException(status_code=502, detail="LiteLLM key spend is unavailable")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=502, detail="LiteLLM key spend is unavailable")
    if not math.isfinite(value) or value < 0:
        raise HTTPException(status_code=502, detail="LiteLLM key spend is unavailable")
    return value


async def current_keys(user_id: str, keys: list[dict] | None = None) -> list[dict]:
    keys = await litellm.list_user_keys(user_id) if keys is None else keys
    semaphore = asyncio.Semaphore(5)

    async def read(key):
        identifier = key.get("token") or key.get("api_key") or key.get("key")
        if not identifier:
            raise HTTPException(status_code=502, detail="Cannot verify a key without its identifier")
        async with semaphore:
            info = await litellm.get_key_info(identifier)
        if not info or info.get("user_id") != user_id:
            raise HTTPException(status_code=502, detail="Could not verify key ownership")
        # Live metadata must not replace (or introduce) lookup identifiers.
        metadata = {name: value for name, value in info.items() if name not in {"token", "api_key", "key"}}
        return {**key, **metadata, "spend": counter(info)}

    return await asyncio.gather(*(read(key) for key in keys))


def _period_advanced(before: dict, after: dict) -> bool:
    try:
        timestamps = [datetime.fromisoformat(info["budget_reset_at"]) for info in (before, after)]
    except (KeyError, TypeError, ValueError):
        return False
    earlier, later = [value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value for value in timestamps]
    return later > earlier


async def verify_replacement(user_id: str, existing: list[dict], replacement: str) -> None:
    # Read again after policy writes. A real period reset must not be undone by
    # copying an earlier snapshot or historical user usage into a current counter.
    source = await current_keys(user_id, existing)
    for before, after in zip(existing, source):
        if counter(after) < counter(before) and not _period_advanced(before, after):
            raise HTTPException(status_code=502, detail="Source key spend decreased without a verified period reset; original keys were kept")
    info = await litellm.get_key_info(replacement)
    expected = sum(counter(key) for key in source)
    if not info or info.get("user_id") != user_id or not math.isclose(counter(info), expected, rel_tol=1e-12, abs_tol=1e-12):
        raise HTTPException(status_code=502, detail="LiteLLM did not preserve replacement key spend; original keys were kept")
