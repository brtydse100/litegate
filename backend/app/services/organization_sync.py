"""Reconcile Helm-managed policy without resetting LiteLLM's spend counters."""

import asyncio
import logging
from weakref import WeakValueDictionary

from fastapi import HTTPException

from app.config import settings
from app.models import CurrentUser
from app.organization import MembershipConflict, OrganizationNode
from app.services import audit, litellm
from app.services import organization_client as upstream, organization_store as store

_logger = logging.getLogger(__name__)
_locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = WeakValueDictionary()


def lock_for(kind: str, identifier: str) -> asyncio.Lock:
    key = (kind, identifier)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def resolve(user_id: str, groups: list[str]) -> OrganizationNode | None:
    try:
        return settings.organization_hierarchy.resolve(user_id, groups)
    except MembershipConflict as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def policy(node: OrganizationNode) -> dict:
    return {"node_id": node.id, "per_user": node.per_user, "duration": node.duration}


async def record_identity(user_id: str, email: str, source: str, groups: list[str]) -> OrganizationNode | None:
    """Persist verified claims even when they invalidate an existing membership."""
    if not settings.organization_hierarchy.levels:
        return None
    async with lock_for("user", user_id):
        previous = await asyncio.to_thread(store.get, user_id)
        try:
            node = resolve(user_id, groups)
            if node is not None or previous:
                await asyncio.to_thread(store.remember, user_id, email, source, groups)
            if node is None and previous:
                raise HTTPException(status_code=403, detail="Your managed organization mapping was removed; contact an administrator")
        except HTTPException as exc:
            await asyncio.to_thread(store.remember, user_id, email, source, groups)
            await asyncio.to_thread(store.failed, user_id, str(exc.detail))
            raise
        return node


async def remember(user_id: str, email: str, source: str, groups: list[str]) -> OrganizationNode | None:
    node = await record_identity(user_id, email, source, groups)
    if node is None:
        return None
    return await synchronize_user(user_id)


async def synchronize_user(user_id: str) -> OrganizationNode | None:
    """Finish provisioning from current stored claims without rewriting them."""
    if not settings.organization_hierarchy.levels:
        return None
    async with lock_for("user", user_id):
        identity = await asyncio.to_thread(store.get, user_id)
        return await synchronize(identity) if identity else None


async def sync_root(node: OrganizationNode) -> dict:
    root = next(root for root in settings.organization_hierarchy.roots if root.team_id == node.team_id)
    async with lock_for("team", root.team_id):
        return await upstream.sync_root(root)


async def synchronize(identity: dict) -> OrganizationNode:
    try:
        node = resolve(identity["user_id"], identity["groups"])
        if node is None:
            raise HTTPException(status_code=403, detail="Your organization mapping is no longer valid")
        return await sync_identity(identity, await sync_root(node))
    except HTTPException as exc:
        await asyncio.to_thread(store.failed, identity["user_id"], str(exc.detail))
        raise


async def sync_identity(identity: dict, info: dict) -> OrganizationNode:
    node = resolve(identity["user_id"], identity["groups"])
    if node is None:
        raise HTTPException(status_code=409, detail="Organization mapping was removed; review the user's keys before changing membership")
    existing = await litellm.list_user_keys(identity["user_id"])
    previous_team = identity.get("team_id")
    if previous_team and previous_team != node.team_id:
        if upstream.membership(info, identity["user_id"]) is None:
            raise HTTPException(
                status_code=409, detail="Top-level organization changed; migrate the user's LiteLLM membership before applying its new budget"
            )
        previous = await upstream.team_info(previous_team)
        roster = (previous.get("team_info") or {}).get("members_with_roles")
        if not isinstance(roster, list):
            raise HTTPException(status_code=502, detail="Could not verify the user's previous LiteLLM membership")
        if upstream.membership(previous, identity["user_id"]) or any(member.get("user_id") == identity["user_id"] for member in roster):
            raise HTTPException(
                status_code=409,
                detail="Top-level organization changed; an administrator must remove the previous LiteLLM membership after reviewing spend",
            )
    if any(key.get("team_id") and key["team_id"] != node.team_id for key in existing):
        raise HTTPException(
            status_code=409, detail="Existing keys belong to another team; migrate them in LiteLLM before changing the top-level organization"
        )
    await asyncio.to_thread(store.bind_team, identity["user_id"], node.team_id)
    await upstream.sync_member(node, identity["user_id"], info)
    for key in existing:
        identifier = key.get("token") or key.get("api_key") or key.get("key")
        if not identifier:
            raise HTTPException(status_code=502, detail="Cannot synchronize a managed key without its identifier")
        if key.get("team_id") != node.team_id or key.get("max_budget") is not None or key.get("budget_duration") is not None:
            await litellm.update_key(identifier, {"team_id": node.team_id, "max_budget": None, "budget_duration": None})
            verified = await litellm.get_key_info(identifier)
            if (
                not verified
                or verified.get("team_id") != node.team_id
                or verified.get("max_budget") is not None
                or verified.get("budget_duration") is not None
            ):
                raise HTTPException(status_code=502, detail="Could not verify the managed key's budget policy")
    changed = identity.get("policy") != policy(node) or identity.get("team_id") != node.team_id
    await asyncio.to_thread(store.synced, identity["user_id"], node.team_id, policy(node))
    if changed:
        await asyncio.to_thread(
            audit.record,
            actor_id="system:organization",
            actor_email="",
            action="organization.policy_sync",
            target=identity["user_id"],
            details={"path": list(node.path), "per_user": node.per_user},
        )
    return node


async def prepare_user(user_id: str, email: str) -> OrganizationNode | None:
    if not settings.organization_hierarchy.levels:
        return None
    identity = await asyncio.to_thread(store.get, user_id)
    if identity is None:
        node = resolve(user_id, [])
        if node is None:
            return None
        await asyncio.to_thread(store.remember, user_id, email, "explicit", [])
        identity = await asyncio.to_thread(store.get, user_id)
    node = resolve(user_id, identity["groups"])
    if node is None:
        raise HTTPException(status_code=403, detail="Your organization mapping is no longer valid")
    return await synchronize(identity)


async def generate_key(user_id: str, email: str, team_id: str | None, **options) -> dict:
    async with lock_for("user", user_id):
        node = await prepare_user(user_id, email)
        if node is None:
            return await litellm.generate_key(user_id, email, team_id, **options)
        return await upstream.generate_key(user_id, email, node.team_id, **options)


async def reconcile() -> None:
    if not settings.organization_hierarchy.levels:
        return
    identities = await asyncio.to_thread(store.list_identities)
    known = {identity["user_id"] for identity in identities}
    ready: set[str] = set()
    semaphore = asyncio.Semaphore(5)

    async def prepare_root(root):
        async with semaphore:
            try:
                await sync_root(root)
                ready.add(root.team_id)
            except HTTPException as exc:
                _logger.warning("Organization root %s synchronization failed: %s", root.team_id, exc.detail)

    await asyncio.gather(*(prepare_root(root) for root in settings.organization_hierarchy.roots))

    async def sync_one(user_id: str):
        async with semaphore, lock_for("user", user_id):
            try:
                identity = await asyncio.to_thread(store.get, user_id)
                node = resolve(user_id, identity["groups"])
                if node is None or node.team_id not in ready:
                    raise HTTPException(status_code=409, detail="Organization mapping or its LiteLLM team is unavailable")
                await sync_identity(identity, await upstream.team_info(node.team_id))
            except HTTPException as exc:
                await asyncio.to_thread(store.failed, user_id, str(exc.detail))

    await asyncio.gather(*(sync_one(identity["user_id"]) for identity in identities))

    async def discover(user_id: str):
        async with semaphore, lock_for("user", user_id):
            try:
                if await asyncio.to_thread(store.get, user_id) is None:
                    existing = await litellm.get_user(user_id)
                    if not existing:
                        return None
                    user = existing.get("user_info", existing)
                    await asyncio.to_thread(store.remember, user_id, user.get("user_email") or "", "explicit", [])
                return user_id
            except HTTPException as exc:
                _logger.warning("Organization user %s discovery failed: %s", user_id, exc.detail)
                return None

    explicit = {user_id for node in settings.organization_hierarchy.nodes.values() for user_id in node.member.userIds}
    discovered = await asyncio.gather(*(discover(user_id) for user_id in sorted(explicit - known)))
    await asyncio.gather(*(sync_one(user_id) for user_id in discovered if user_id is not None))


async def run_reconciliation() -> None:
    while True:
        try:
            await reconcile()
        except Exception:
            _logger.exception("Organization synchronization failed")
        await asyncio.sleep(60)


def guard_team(team_id: str, changes: dict | None = None) -> None:
    if settings.organization_hierarchy.is_managed_team(team_id) and (changes is None or {"max_budget", "budget_duration"}.intersection(changes)):
        raise HTTPException(status_code=409, detail="This team's membership and budget are managed by organizationHierarchy")


async def guard_key(key: str, changes: dict) -> None:
    if not settings.organization_hierarchy.levels or not {"team_id", "max_budget", "budget_duration"}.intersection(changes):
        return
    info = await litellm.get_key_info(key)
    if not info:
        raise HTTPException(status_code=404, detail="Key not found")
    identity = await asyncio.to_thread(store.get, info.get("user_id") or "")
    if (
        settings.organization_hierarchy.is_managed_team(info.get("team_id"))
        or settings.organization_hierarchy.is_managed_team(changes.get("team_id"))
        or (identity and identity.get("team_id"))
    ):
        raise HTTPException(status_code=409, detail="This key's team and budget are managed by organizationHierarchy")


async def personal_policy(user: CurrentUser, keys: list[dict] | None = None) -> dict | None:
    if not settings.organization_hierarchy.levels:
        return None
    identity = await asyncio.to_thread(store.get, user.user_id)
    error = identity.get("sync_error") if identity else None
    try:
        node = resolve(user.user_id, identity["groups"] if identity else [])
    except HTTPException as exc:
        node, error = None, str(exc.detail)
    team_id = next((key["team_id"] for key in keys or [] if settings.organization_hierarchy.is_managed_team(key.get("team_id"))), None)
    team_id = team_id or (identity.get("team_id") if identity else None) or (node.team_id if node else None)
    if team_id is None:
        return None
    root = next((root for root in settings.organization_hierarchy.roots if root.team_id == team_id), None)
    valid = node is not None and node.team_id == team_id
    result = {
        "path": list(node.path) if valid else list(root.path) if root else [],
        "per_user": None,
        "duration": None,
        "spend": None,
        "budget_available": False,
        "sync_error": error,
    }
    if not valid:
        result["sync_error"] = error or "Your organization mapping was removed or changed; contact an administrator"
    if any(key.get("team_id") != team_id for key in keys or []):
        result["sync_error"] = result["sync_error"] or "Your key's team assignment is not synchronized; its user allowance is unavailable"
        return result
    try:
        actual = upstream.member_budget(await upstream.team_info(team_id), user.user_id)
        result.update(actual, budget_available=True)
        if valid and (actual["per_user"] != node.per_user or actual["duration"] != node.duration):
            result["sync_error"] = result["sync_error"] or "Your enforced allowance differs from organizationHierarchy; contact an administrator"
        if any(key.get("max_budget") is not None or key.get("budget_duration") is not None for key in keys or []):
            result["sync_error"] = result["sync_error"] or "Your key still has an additional LiteLLM budget restriction; contact an administrator"
    except HTTPException as exc:
        result["sync_error"] = result["sync_error"] or str(exc.detail)
    return result
