"""Every stored identity resolved to its group, shared by organization views.

Organization pages need each member's group to count and list members.
Resolving every identity on every request costs a full table read plus a
resolution per person, so one resolved list is reused until an identity is
written, the hierarchy is replaced, or ``TTL`` seconds pass (allowance shares
also change when other people join a group).
"""

import asyncio
from collections import Counter
from time import monotonic

from fastapi import HTTPException

from app.config import settings
from app.services import organization_store as store

TTL = 10

_cache: dict = {}
_lock = asyncio.Lock()


def clear() -> None:
    _cache.clear()


def _resolve_all() -> list[tuple[dict, object, str | None]]:
    from app.services.organization_sync import resolve_identity

    rows = []
    for identity in store.list_identities():
        try:
            rows.append((identity, resolve_identity(identity), None))
        except HTTPException as exc:
            rows.append((identity, None, str(exc.detail)))
    return rows


async def resolved() -> list[tuple[dict, object, str | None]]:
    """(identity, group or None, resolution error) for every stored identity."""
    async with _lock:
        version, tree = store.version(), settings.organization_hierarchy
        if _cache.get("version") == version and _cache.get("tree") is tree and monotonic() - _cache["at"] < TTL:
            return _cache["rows"]
        rows = await asyncio.to_thread(_resolve_all)
        # Keyed on the version read before resolving, so a concurrent write
        # forces the next request to resolve again.
        _cache.update(version=version, tree=tree, rows=rows, at=monotonic())
        return rows


def member_counts(records) -> Counter:
    """Members per group path, counting each person in every enclosing group."""
    counts: Counter = Counter()
    for _, node in records:
        for depth in range(1, len(node.path) + 1):
            counts[node.path[:depth]] += 1
    return counts
