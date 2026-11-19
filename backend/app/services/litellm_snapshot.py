"""Shared, short-lived bulk reads of LiteLLM teams and keys for reports.

Organization reports read these instead of sending one LiteLLM request per
group or person. Each snapshot refreshes at most once per ``TTL`` seconds and
concurrent callers share a single refresh, so the number of open pages does not
multiply upstream load. A failed refresh is remembered for the same ``TTL`` so
an outage or an oversized installation does not trigger a listing per caller.
Key writes and budget enforcement keep reading live.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from weakref import WeakKeyDictionary

from fastapi import HTTPException

from app.services import litellm

_logger = logging.getLogger(__name__)

TTL = 60
PAGE_SIZE = 100
MAX_PAGES = 200  # 20,000 records; larger installations fall back to per-item reads.


class Snapshot:
    def __init__(self, load: Callable[[], Awaitable[dict]]):
        self._load = load
        self._value: dict | None = None
        self._error: HTTPException | None = None
        self._loaded_at: float | None = None
        self._locks: WeakKeyDictionary = WeakKeyDictionary()

    def _fresh(self) -> bool:
        return self._loaded_at is not None and monotonic() - self._loaded_at < TTL

    def _result(self) -> dict:
        if self._error is not None:
            # A fresh exception per caller, so tracebacks do not pile up on one
            # cached object for the whole TTL.
            raise HTTPException(status_code=self._error.status_code, detail=self._error.detail)
        return self._value

    async def get(self) -> dict:
        if self._fresh():
            return self._result()
        lock = self._locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())
        async with lock:
            if not self._fresh():
                try:
                    self._value, self._error = await self._load(), None
                except HTTPException as exc:
                    self._value, self._error = None, exc
                except (TypeError, ValueError):
                    # A malformed listing must fall back like an outage, not 500.
                    _logger.warning("LiteLLM bulk listing was unreadable; reports fall back to per-item reads", exc_info=True)
                    self._value, self._error = None, HTTPException(status_code=502, detail="LiteLLM returned an unreadable listing")
                self._loaded_at = monotonic()
            return self._result()

    def clear(self) -> None:
        self._value, self._error, self._loaded_at = None, None, None


async def _pages(fetch: Callable[[int], Awaitable[dict]], items: str) -> list[dict]:
    records: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        result = await fetch(page)
        total_pages = max(1, int(result.get("total_pages") or 1))
        if total_pages > MAX_PAGES:
            break
        records.extend(item for item in result.get(items) or [] if isinstance(item, dict))
        if page >= total_pages:
            return records
    raise HTTPException(status_code=409, detail="Too many LiteLLM records for a bulk snapshot")


async def _load_teams() -> dict:
    teams = await _pages(lambda page: litellm.list_teams(page=page, page_size=PAGE_SIZE), "teams")
    return {team["team_id"]: team for team in teams if isinstance(team.get("team_id"), str)}


async def _load_keys() -> dict:
    keys = await _pages(lambda page: litellm.list_keys(page=page, size=PAGE_SIZE), "keys")
    owners: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for key in keys:
        # Offset paging can repeat a key when one is added mid-listing (counted
        # once here) or skip one when a key is deleted; either corrects itself on
        # the next refresh, at most TTL seconds later.
        token = key.get("token")
        if isinstance(token, str):
            if token in seen:
                continue
            seen.add(token)
        if isinstance(key.get("user_id"), str):
            owners.setdefault(key["user_id"], []).append(key)
    return owners


teams = Snapshot(_load_teams)
keys_by_user = Snapshot(_load_keys)


def clear() -> None:
    teams.clear()
    keys_by_user.clear()
