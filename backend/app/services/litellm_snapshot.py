"""Shared, short-lived bulk reads of LiteLLM teams and keys for reports.

Organization reports read these instead of sending one LiteLLM request per
group or person. Each snapshot refreshes at most once per ``TTL`` seconds and
concurrent callers share a single refresh, so the number of open pages does not
multiply upstream load. Key writes and budget enforcement keep reading live.
"""

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from weakref import WeakKeyDictionary

from fastapi import HTTPException

from app.services import litellm

TTL = 60
PAGE_SIZE = 100
MAX_PAGES = 200  # 20,000 records; larger installations fall back to per-item reads.


class Snapshot:
    def __init__(self, load: Callable[[], Awaitable[dict]]):
        self._load = load
        self._value: dict | None = None
        self._loaded_at: float | None = None
        self._locks: WeakKeyDictionary = WeakKeyDictionary()

    def _fresh(self) -> bool:
        return self._loaded_at is not None and monotonic() - self._loaded_at < TTL

    async def get(self) -> dict:
        if self._fresh():
            return self._value
        lock = self._locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())
        async with lock:
            if not self._fresh():
                self._value = await self._load()
                self._loaded_at = monotonic()
            return self._value

    def clear(self) -> None:
        self._value, self._loaded_at = None, None


async def _pages(fetch: Callable[[int], Awaitable[dict]], items: str) -> list[dict]:
    records: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        result = await fetch(page)
        records.extend(item for item in result.get(items) or [] if isinstance(item, dict))
        if page >= max(1, int(result.get("total_pages") or 1)):
            return records
    raise HTTPException(status_code=409, detail="Too many LiteLLM records for a bulk snapshot")


async def _load_teams() -> dict:
    teams = await _pages(lambda page: litellm.list_teams(page=page, page_size=PAGE_SIZE), "teams")
    return {team["team_id"]: team for team in teams if isinstance(team.get("team_id"), str)}


async def _load_keys() -> dict:
    keys = await _pages(lambda page: litellm.list_keys(page=page, size=PAGE_SIZE), "keys")
    owners: dict[str, list[dict]] = {}
    for key in keys:
        if isinstance(key.get("user_id"), str):
            owners.setdefault(key["user_id"], []).append(key)
    return owners


teams = Snapshot(_load_teams)
keys_by_user = Snapshot(_load_keys)


def clear() -> None:
    teams.clear()
    keys_by_user.clear()
