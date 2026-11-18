"""Minute-by-minute organization reconciliation, one group at a time."""

import asyncio

from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationNode
from app.services import budget_pass, litellm_client, organization_key_policy as key_policy, organization_sync as sync
from app.services import organization_client as upstream, organization_discovery as discovery, organization_store as store


async def reconcile() -> None:
    """Reconcile every member, one organization group at a time.

    Each group's step holds only that group's lock, so sign-ins and key
    replacements elsewhere never wait for a whole pass.
    """
    if not settings.organization_hierarchy.levels:
        return
    verified = budget_pass.generation()
    identities = await asyncio.to_thread(store.list_identities)
    blocked = await discovery.refresh(identities, sync.lock_for, sync.resolve)
    identities = await asyncio.to_thread(store.list_identities)
    ready: set[str] = set()
    semaphore = asyncio.Semaphore(5)

    async def prepare_root(root):
        async with semaphore:
            try:
                async with sync.lock_for("team", root.team_id):
                    await upstream.sync_root(root)
                ready.add(root.team_id)
            except HTTPException as exc:
                sync._logger.warning("Organization root %s synchronization failed: %s", root.team_id, exc.detail)

    await asyncio.gather(*(prepare_root(root) for root in settings.organization_hierarchy.nodes.values()))
    if budget_pass.cross_group_pending():
        # Money moved between groups: apply every decrease before any group raises.
        await budget_pass.full_pass()
    budget_pass.mark_clean(verified)

    groups: dict[str, list[str]] = {}
    for identity in identities:
        user_id = identity["user_id"]
        if user_id in blocked:
            continue
        try:
            node = sync.resolve_identity(identity)
            if node is None or node.team_id not in ready:
                raise HTTPException(status_code=409, detail="Organization mapping or its LiteLLM team is unavailable")
        except HTTPException as exc:
            await asyncio.to_thread(store.failed, user_id, str(exc.detail))
            continue
        groups.setdefault(node.id, []).append(user_id)
    for node_id, members in groups.items():
        await budget_pass.group_pass(node_id, set(members), lambda node_id=node_id, members=members: _reconcile_group(node_id, members))

    async def finish_team(node):
        async with semaphore, sync.lock_for("team", node.team_id):
            if node.team_id in ready:
                try:
                    await key_policy.finish_team(node)
                except HTTPException as exc:
                    sync._logger.warning("Organization team %s migration pending: %s", node.team_id, exc.detail)

    await asyncio.gather(*(finish_team(node) for node in settings.organization_hierarchy.nodes.values()))


async def _reconcile_group(node_id: str, members: list[str]) -> None:
    prepared: dict[str, OrganizationNode] = {}
    semaphore = asyncio.Semaphore(5)

    async def sync_one(user_id: str):
        async with semaphore, sync.lock_for("user", user_id):
            try:
                identity = await asyncio.to_thread(store.get, user_id)
                node = sync.resolve_identity(identity)
                if node is None or node.id != node_id:
                    raise HTTPException(status_code=409, detail="Organization assignment changed during migration; retrying next pass")
                await sync.sync_identity(identity, await upstream.team_info(node.team_id), defer_finalization=True)
                prepared[user_id] = node
            except HTTPException as exc:
                await asyncio.to_thread(store.failed, user_id, str(exc.detail))

    # Establish every member's key policy before attempting to remove shared caps.
    # Otherwise the first users in a team stay failed until the next minute.
    async def finalize_one(user_id: str):
        async with semaphore, sync.lock_for("user", user_id):
            try:
                identity = await asyncio.to_thread(store.get, user_id)
                node = sync.resolve_identity(identity)
                if node is None or (node.id, node.team_id) != (prepared[user_id].id, prepared[user_id].team_id):
                    raise HTTPException(status_code=409, detail="Organization assignment changed during migration; retrying next pass")
                await sync.finalize_identity(identity, node, await budget_pass.keys(user_id))
            except HTTPException as exc:
                await asyncio.to_thread(store.failed, user_id, str(exc.detail))

    with litellm_client.team_cache():
        await asyncio.gather(*(sync_one(user_id) for user_id in members))
        await asyncio.gather(*(finalize_one(user_id) for user_id in prepared))
