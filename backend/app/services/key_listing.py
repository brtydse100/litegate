"""Administrative key search over a bounded, briefly cached installation key set.

A search, team or blocked filter needs every key, because LiteLLM cannot
search all key fields itself. Pages after the first are read concurrently, and
the result is reused for ``TTL`` seconds so paging through results or selecting
"all matching" does not reread the installation. Any key write made through
LiteGate invalidates it; changes made directly in LiteLLM appear within ``TTL``.
"""

import asyncio
from time import monotonic

from fastapi import HTTPException

from app.services import litellm

TTL = 15
PAGE_SIZE = 100
CONCURRENCY = 4

_cache: dict = {}
_lock = asyncio.Lock()


def clear() -> None:
    _cache.clear()


def _limit(max_keys: int) -> HTTPException:
    return HTTPException(status_code=409, detail=f"This installation has more than the administrative safety limit of {max_keys} keys")


async def list_all_keys(max_keys: int = 5000) -> list[dict]:
    """Read an explicitly requested, safety-bounded installation key set."""
    first = await litellm.list_keys(page=1, size=PAGE_SIZE)
    total_pages = max(1, int(first.get("total_pages", 1)))
    if int(first.get("total", 0)) > max_keys or total_pages > (max_keys + PAGE_SIZE - 1) // PAGE_SIZE:
        raise _limit(max_keys)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def page(number: int) -> dict:
        async with semaphore:
            return await litellm.list_keys(page=number, size=PAGE_SIZE)

    results = [first, *await asyncio.gather(*(page(number) for number in range(2, total_pages + 1)))]
    records: list[dict] = []
    seen: set[str] = set()
    for result in results:
        for key in result.get("keys", []):
            if not isinstance(key, dict):
                continue
            # Offset paging can repeat a key that was added during the read.
            token = key.get("token")
            if isinstance(token, str):
                if token in seen:
                    continue
                seen.add(token)
            records.append(key)
    if len(records) > max_keys:
        raise _limit(max_keys)
    return records


async def _cached_keys(max_keys: int) -> list[dict]:
    async with _lock:
        writes = litellm.key_writes()
        if _cache.get("writes") == writes and _cache.get("max_keys") == max_keys and monotonic() - _cache["at"] < TTL:
            return _cache["keys"]
        keys = await list_all_keys(max_keys=max_keys)
        _cache.update(keys=keys, writes=writes, max_keys=max_keys, at=monotonic())
        return keys


def _filter_keys(
    keys: list[dict],
    *,
    search: str = "",
    team_id: str = "",
    blocked: bool | None = None,
) -> list[dict]:
    normalized_search = search.strip().casefold()
    normalized_team = team_id.strip().casefold()
    filtered: list[dict] = []
    for key in keys:
        if normalized_search:
            values = (
                key.get("key_alias"),
                key.get("user_email"),
                key.get("user_id"),
                key.get("team_id"),
                key.get("token"),
                key.get("api_key"),
                key.get("key"),
            )
            if not any(normalized_search in str(value).casefold() for value in values if value):
                continue
        if normalized_team and str(key.get("team_id") or "").casefold() != normalized_team:
            continue
        if blocked is not None and bool(key.get("blocked")) is not blocked:
            continue
        filtered.append(key)
    return filtered


async def list_keys_filtered(
    *,
    page: int = 1,
    size: int = 50,
    search: str = "",
    team_id: str = "",
    blocked: bool | None = None,
    max_keys: int = 5000,
) -> dict:
    """Return a global filtered page; unfiltered requests stay natively paginated."""
    if not search.strip() and not team_id.strip() and blocked is None:
        return await litellm.list_keys(page=page, size=size)
    filtered = _filter_keys(await _cached_keys(max_keys), search=search, team_id=team_id, blocked=blocked)
    start = (page - 1) * size
    total = len(filtered)
    return {
        "keys": filtered[start : start + size],
        "page": page,
        "size": size,
        "total": total,
        "total_pages": max(1, (total + size - 1) // size),
    }


async def list_key_identifiers(
    max_keys: int = 5000,
    *,
    search: str = "",
    team_id: str = "",
    blocked: bool | None = None,
) -> list[str]:
    """Return every matching key identifier."""
    identifiers: list[str] = []
    seen: set[str] = set()
    for key in _filter_keys(await _cached_keys(max_keys), search=search, team_id=team_id, blocked=blocked):
        identifier = key.get("token") or key.get("api_key") or key.get("key")
        if identifier and str(identifier) not in seen:
            seen.add(str(identifier))
            identifiers.append(str(identifier))
    return identifiers
