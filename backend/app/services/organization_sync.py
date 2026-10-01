"""Reconcile Helm-managed policy without resetting LiteLLM's spend counters."""

import asyncio
import logging

from fastapi import HTTPException

from app.config import settings
from app.models import CurrentUser
from app.organization import MembershipConflict, OrganizationNode
from app.services import audit, litellm
from app.services import organization_client as upstream, organization_store as store

_logger = logging.getLogger(__name__)
_lock = asyncio.Lock()


def resolve(user_id: str, groups: list[str]) -> OrganizationNode | None:
    try:
        return settings.organization_hierarchy.resolve(user_id, groups)
    except MembershipConflict as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def policy(node: OrganizationNode) -> dict:
    return {"node_id": node.id, "per_user": node.per_user, "duration": node.duration}


async def remember(user_id: str, email: str, source: str, groups: list[str]) -> OrganizationNode | None:
    if not settings.organization_hierarchy.levels:
        return None
    node = resolve(user_id, groups)
    previous = await asyncio.to_thread(store.get, user_id)
    if node is None and previous and previous.get("team_id"):
        raise HTTPException(status_code=403, detail="Your managed organization mapping was removed; contact an administrator")
    if node is not None:
        await asyncio.to_thread(store.remember, user_id, email, source, groups)
        async with _lock:
            await synchronize(await asyncio.to_thread(store.get, user_id))
    return node


async def synchronize(identity: dict) -> OrganizationNode:
    try:
        node = resolve(identity["user_id"], identity["groups"])
        if node is None:
            raise HTTPException(status_code=403, detail="Your organization mapping is no longer valid")
        root = next(root for root in settings.organization_hierarchy.roots if root.team_id == node.team_id)
        return await sync_identity(identity, await upstream.sync_root(root))
    except HTTPException as exc:
        await asyncio.to_thread(store.failed, identity["user_id"], str(exc.detail))
        raise


async def sync_identity(identity: dict, info: dict) -> OrganizationNode:
    node = resolve(identity["user_id"], identity["groups"])
    if node is None:
        raise HTTPException(status_code=409, detail="Organization mapping was removed; review the user's keys before changing membership")
    existing = await litellm.list_user_keys(identity["user_id"])
    if identity.get("team_id") and identity["team_id"] != node.team_id and upstream.membership(info, identity["user_id"]) is None:
        raise HTTPException(
            status_code=409, detail="Top-level organization changed; migrate the user's LiteLLM membership before applying its new budget"
        )
    if any(key.get("team_id") and key["team_id"] != node.team_id for key in existing):
        raise HTTPException(
            status_code=409, detail="Existing keys belong to another team; migrate them in LiteLLM before changing the top-level organization"
        )
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
        return await remember(user_id, email, "explicit", [])
    node = resolve(user_id, identity["groups"])
    if node is None:
        raise HTTPException(status_code=403, detail="Your organization mapping is no longer valid")
    async with _lock:
        return await synchronize(identity)


async def generate_key(user_id: str, email: str, team_id: str | None, **options) -> dict:
    node = await prepare_user(user_id, email)
    if node is None:
        return await litellm.generate_key(user_id, email, team_id, **options)
    return await upstream.generate_key(user_id, email, node.team_id, **options)


async def reconcile() -> None:
    if not settings.organization_hierarchy.levels:
        return
    async with _lock:
        identities = await asyncio.to_thread(store.list_identities)
        known = {identity["user_id"] for identity in identities}
        for node in settings.organization_hierarchy.nodes.values():
            for user_id in node.member.userIds:
                if user_id not in known:
                    existing = await litellm.get_user(user_id)
                    if existing:
                        user = existing.get("user_info", existing)
                        await asyncio.to_thread(store.remember, user_id, user.get("user_email") or "", "explicit", [])
                        known.add(user_id)
        identities = await asyncio.to_thread(store.list_identities)
        infos: dict[str, dict] = {}
        for root in settings.organization_hierarchy.roots:
            try:
                infos[root.team_id] = await upstream.sync_root(root)
            except HTTPException as exc:
                _logger.warning("Organization root %s synchronization failed: %s", root.team_id, exc.detail)
        semaphore = asyncio.Semaphore(5)

        async def sync_one(identity: dict):
            async with semaphore:
                try:
                    node = resolve(identity["user_id"], identity["groups"])
                    if node is None or node.team_id not in infos:
                        raise HTTPException(status_code=409, detail="Organization mapping or its LiteLLM team is unavailable")
                    await sync_identity(identity, infos[node.team_id])
                except HTTPException as exc:
                    await asyncio.to_thread(store.failed, identity["user_id"], str(exc.detail))

        await asyncio.gather(*(sync_one(identity) for identity in identities))


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


async def personal_policy(user: CurrentUser) -> dict | None:
    if not settings.organization_hierarchy.levels:
        return None
    identity = await asyncio.to_thread(store.get, user.user_id)
    node = resolve(user.user_id, identity["groups"] if identity else [])
    if node is None:
        return None
    info = await upstream.team_info(node.team_id)
    member = upstream.membership(info, user.user_id)
    if member is None:
        raise HTTPException(status_code=502, detail="Could not read your managed LiteLLM membership")
    return {
        "path": list(node.path),
        "per_user": node.per_user,
        "duration": node.duration,
        "spend": upstream.finite_number(member.get("spend")),
        "sync_error": identity.get("sync_error") if identity else None,
    }
