"""Serialize enforced policy writes with fresh spend and decreases first."""

import asyncio
import contextvars
from functools import wraps
from weakref import WeakKeyDictionary

from fastapi import HTTPException

from app.config import settings
from app.organization import MembershipConflict
from app.services import budget_enforcement as enforcement, budget_key_guards, key_spend, litellm, organization_store as store

_locks = WeakKeyDictionary()
_observed = contextvars.ContextVar("budget_pass_keys", default=None)


async def keys(user_id: str) -> list[dict]:
    cached = _observed.get()
    if cached is not None and user_id in cached:
        return cached[user_id]
    return await litellm.list_user_keys(user_id)


def _node(identity):
    try:
        return settings.organization_hierarchy.resolve(
            identity["user_id"], identity["groups"], email=identity["email"], source=identity["auth_source"]
        )
    except MembershipConflict as exc:
        raise HTTPException(409, "Resolve conflicting memberships before applying budget changes") from exc


async def _collect(identities):
    observations = {}
    semaphore = asyncio.Semaphore(5)

    async def one(identity):
        if _node(identity) is None:
            if identity.get("team_id"):
                raise HTTPException(409, "Resolve removed organization mappings before reallocating budgets")
            return
        async with semaphore:
            user_id = identity["user_id"]
            current = await litellm.list_user_keys(user_id)
            budget_key_guards.guard_single_key(current)
            for key in current:
                key_spend.counter(key)  # Unknown spend must never become zero.
            await enforcement.observe(user_id, current)
            observations[user_id] = current

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


def serialized(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        if not enforcement.enforced() or _observed.get() is not None:
            return await function(*args, **kwargs)
        loop = asyncio.get_running_loop()
        lock = _locks.setdefault(loop, asyncio.Lock())
        async with lock:
            identities = await asyncio.to_thread(store.list_identities)
            observations = await _collect(identities)
            token = await enforcement.pin()
            cache_token = _observed.set(observations)
            try:
                await _decrease(identities, observations)
                return await function(*args, **kwargs)
            finally:
                _observed.reset(cache_token)
                enforcement.unpin(token)

    return wrapped
