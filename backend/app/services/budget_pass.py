"""Serialize enforced policy writes with fresh spend and decreases first."""

import asyncio
import contextvars
from functools import wraps
from inspect import signature
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


def serialized(function=None, *, provision=False):
    if function is None:
        return lambda operation: serialized(operation, provision=provision)

    @wraps(function)
    async def wrapped(*args, **kwargs):
        if not enforcement.enforced() or _observed.get() is not None:
            return await function(*args, **kwargs)
        loop = asyncio.get_running_loop()
        lock = _locks.setdefault(loop, asyncio.Lock())
        async with lock:
            if provision:
                arguments = signature(function).bind(*args, **kwargs).arguments
                user_id, email = arguments["user_id"], arguments["email"]
                identity = await asyncio.to_thread(store.get, user_id)
                if identity is None:
                    identity = {"user_id": user_id, "email": email, "auth_source": "explicit", "groups": []}
                    if _node(identity) is not None:
                        await asyncio.to_thread(store.remember, user_id, email, "explicit", [])
                if _node(identity) is not None:
                    await asyncio.to_thread(enforcement.mark_participant, user_id)
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
