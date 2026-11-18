"""Serialize enforced policy writes with fresh spend and decreases first.

Shares are computed per organization group: a group's members split its own
amount, so writes for different groups cannot fund each other. Each operation
therefore locks only the groups it can change (the member's current group, the
group they came from and the groups their keys are in) and re-reads only those
members' keys; operations on other groups run in parallel.

Moving money between groups (an assigned-total edit) is the exception: until a
full pass has applied the resulting decreases, operations take the exclusive
lock and read every member, so no increase can precede another group's
decrease.
"""

import asyncio
import contextvars
from contextlib import asynccontextmanager
from functools import wraps
from inspect import signature
from weakref import WeakKeyDictionary

from fastapi import HTTPException

from app.config import settings
from app.organization import MembershipConflict
from app.services import budget_enforcement as enforcement, budget_key_guards, key_spend, litellm, organization_store as store

_gates = WeakKeyDictionary()
_observed = contextvars.ContextVar("budget_pass_keys", default=None)
# Cross-group edits since the last full pass; a new process starts unverified.
_generation = 1
_clean = 0


def mark_cross_group_edit() -> None:
    global _generation
    _generation += 1


def generation() -> int:
    return _generation


def mark_clean(verified: int) -> None:
    global _clean
    _clean = max(_clean, verified)


def cross_group_pending() -> bool:
    return _clean < _generation


async def keys(user_id: str) -> list[dict]:
    cached = _observed.get()
    if cached is not None and user_id in cached:
        return cached[user_id]
    return await litellm.list_user_keys(user_id)


class _Gate:
    """Exclusive full passes, otherwise per-group locks taken in sorted order."""

    def __init__(self):
        self.condition = asyncio.Condition()
        self.exclusive = False
        self.shared = 0
        self.waiting = 0
        self.groups: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def hold(self, groups: set[str] | None):
        async with self.condition:
            if groups is None:
                self.waiting += 1
                try:
                    await self.condition.wait_for(lambda: not self.exclusive and not self.shared)
                finally:
                    self.waiting -= 1
                self.exclusive = True
            else:
                await self.condition.wait_for(lambda: not self.exclusive and not self.waiting)
                self.shared += 1
        acquired = []
        try:
            for group in sorted(groups or ()):
                lock = self.groups.setdefault(group, asyncio.Lock())
                await lock.acquire()
                acquired.append(lock)
            yield
        finally:
            for lock in reversed(acquired):
                lock.release()
            async with self.condition:
                if groups is None:
                    self.exclusive = False
                else:
                    self.shared -= 1
                self.condition.notify_all()


def _gate() -> _Gate:
    return _gates.setdefault(asyncio.get_running_loop(), _Gate())


class _Widen(Exception):
    """The operation reaches groups it did not lock; retry exclusively."""


def _node(identity):
    try:
        return settings.organization_hierarchy.resolve(
            identity["user_id"], identity["groups"], email=identity["email"], source=identity["auth_source"]
        )
    except MembershipConflict as exc:
        raise HTTPException(409, "Resolve conflicting memberships before applying budget changes") from exc


def _resolved(identity):
    try:
        return _node(identity)
    except HTTPException:
        return None


def _groups_for(user_id: str, identities: list[dict], current_keys: list[dict]) -> set[str]:
    tree = settings.organization_hierarchy
    groups, teams = set(), {key.get("team_id") for key in current_keys}
    identity = next((item for item in identities if item["user_id"] == user_id), None)
    if identity is not None:
        node = _node(identity)
        teams.add(identity.get("team_id"))
    else:
        node = tree.resolve(user_id, [])
    if node is not None:
        groups.add(node.id)
    previous = enforcement.membership(user_id)
    if previous:
        groups.add(previous)
    groups.update(item.id for item in tree.nodes.values() if item.team_id in teams)
    return groups


async def _collect(identities):
    observations = {}
    semaphore = asyncio.Semaphore(5)

    async def one(identity):
        node = _node(identity)
        if node is None:
            if identity.get("team_id"):
                raise HTTPException(409, "Resolve removed organization mappings before reallocating budgets")
            return
        async with semaphore:
            user_id = identity["user_id"]
            current = await litellm.list_user_keys(user_id)
            budget_key_guards.guard_single_key(current)
            verified_keys = []
            for key in current:
                if "team_id" not in key or "user_id" not in key:
                    key = (await key_spend.current_keys(user_id, [key]))[0]
                if key.get("user_id") != user_id or "team_id" not in key:
                    raise HTTPException(502, "Cannot verify key ownership and source team; no budget changes applied")
                if key["team_id"] is not None and (not isinstance(key["team_id"], str) or not key["team_id"].strip()):
                    raise HTTPException(502, "Cannot verify key source team; no budget changes applied")
                key_spend.counter(key)  # Unknown spend must never become zero.
                # A key still in a member's previous managed group is a transfer:
                # spend floors follow the member, so the new group counts what was
                # already used and sign-in or the next sync moves the key there.
                verified_keys.append(key)
            await enforcement.observe(user_id, verified_keys)
            observations[user_id] = verified_keys

    # A failed read aborts before any cap is raised. Do not swallow failures.
    results = await asyncio.gather(*(one(identity) for identity in identities), return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return observations


async def _decrease(identities, observations):
    for identity in identities:
        node = _node(identity)
        if node is None:
            continue
        target = enforcement.allowance(node, identity["user_id"]).per_user
        for key in observations.get(identity["user_id"], []):
            if target is None:
                continue
            if "max_budget" not in key:
                raise HTTPException(502, "Current key budget is unavailable; no budget increases applied")
            if key["max_budget"] is not None and key["max_budget"] <= target:
                continue
            identifier = key.get("token") or key.get("api_key") or key.get("key")
            if not identifier:
                raise HTTPException(502, "Cannot verify a key without its identifier")
            await litellm.update_key(identifier, {"max_budget": target})
            verified = await litellm.get_key_info(identifier)
            if not verified or verified.get("user_id") != identity["user_id"] or verified.get("max_budget") != target:
                raise HTTPException(502, "Could not verify budget decrease; no budget increases applied")
            key["max_budget"] = target


async def _run(groups: set[str] | None, operation, *, user_id: str | None = None, members: set[str] | None = None):
    """Lock ``groups`` (all when None), observe their members, then decrease first."""
    async with _gate().hold(groups):
        identities = await asyncio.to_thread(store.list_identities)
        if groups is None:
            chosen = identities
        else:
            chosen = []
            for identity in identities:
                if identity["user_id"] == user_id or (members is not None and identity["user_id"] in members):
                    chosen.append(identity)
                elif members is None and (node := _resolved(identity)) is not None and node.id in groups:
                    chosen.append(identity)
        observations = await _collect(chosen)
        if user_id is not None and groups is not None:
            current = observations.get(user_id)
            if current is None:
                current = await litellm.list_user_keys(user_id)
            if not _groups_for(user_id, identities, current) <= groups:
                raise _Widen
        token = await enforcement.pin()
        cache_token = _observed.set(observations)
        try:
            await _decrease(chosen, observations)
            return await operation()
        finally:
            _observed.reset(cache_token)
            enforcement.unpin(token)


async def group_pass(node_id: str, members: set[str], operation):
    """Run one group's reconciliation step under that group's lock only."""
    if not enforcement.enforced() or _observed.get() is not None:
        return await operation()
    return await _run({node_id}, operation, members=members)


async def full_pass(operation=None):
    """Observe every member and apply every decrease under the exclusive lock."""

    async def nothing():
        return None

    if not enforcement.enforced():
        return await (operation or nothing)()
    return await _run(None, operation or nothing)


def serialized(function=None, *, provision=False):
    if function is None:
        return lambda operation: serialized(operation, provision=provision)

    @wraps(function)
    async def wrapped(*args, **kwargs):
        if not enforcement.enforced() or _observed.get() is not None:
            return await function(*args, **kwargs)
        arguments = signature(function).bind(*args, **kwargs).arguments
        user_id = arguments.get("user_id")
        if provision:
            email = arguments["email"]
            identity = await asyncio.to_thread(store.get, user_id)
            if identity is None:
                identity = {"user_id": user_id, "email": email, "auth_source": "explicit", "groups": []}
                if _node(identity) is not None:
                    await asyncio.to_thread(store.remember, user_id, email, "explicit", [])
            if _node(identity) is not None:
                await asyncio.to_thread(enforcement.mark_participant, user_id)

        async def operation():
            return await function(*args, **kwargs)

        if user_id is None or cross_group_pending():
            return await _run(None, operation, user_id=user_id)
        identities = await asyncio.to_thread(store.list_identities)
        groups = _groups_for(user_id, identities, await litellm.list_user_keys(user_id))
        try:
            return await _run(groups, operation, user_id=user_id)
        except _Widen:
            return await _run(None, operation, user_id=user_id)

    return wrapped
