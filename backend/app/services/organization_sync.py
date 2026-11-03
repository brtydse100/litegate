"""Reconcile Helm-managed policy without resetting LiteLLM's spend counters."""

import asyncio
import logging
from secrets import token_hex
from weakref import WeakValueDictionary

from fastapi import HTTPException

from app.config import settings
from app.models import CurrentUser
from app.organization import MembershipConflict, OrganizationNode
from app.services import audit, key_cleanup, litellm, organization_key_policy as key_policy
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
    info = {}
    for ancestor in settings.organization_hierarchy.nodes.values():
        if node.path[: len(ancestor.path)] == ancestor.path:
            async with lock_for("team", ancestor.team_id):
                info = await upstream.sync_root(ancestor)
    return info


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
    ancestor_teams = {
        ancestor.team_id for ancestor in settings.organization_hierarchy.nodes.values() if node.path[: len(ancestor.path)] == ancestor.path
    }
    if len(existing) > 500:
        raise HTTPException(status_code=409, detail="User has more than the safe migration limit of 500 keys")
    await key_policy.guard_ancestor_restrictions(node, identity["user_id"], existing)
    await asyncio.to_thread(store.bind_team, identity["user_id"], node.team_id)
    for ancestor in settings.organization_hierarchy.nodes.values():
        if ancestor.team_id in ancestor_teams:
            current = info if ancestor.team_id == node.team_id else await upstream.team_info(ancestor.team_id)
            if upstream.membership(current, identity["user_id"]) is None:
                await litellm.add_team_member(ancestor.team_id, identity["user_id"])
    for key in existing:
        await key_policy.apply_key(node, key)
    if existing:
        async with lock_for("team", node.team_id):
            await key_policy.normalize_individual_caps(node, identity["user_id"])
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
        return await _generate_key(user_id, email, team_id, **options)


async def _generate_key(user_id: str, email: str, team_id: str | None, **options) -> dict:
    """Generate while the caller holds the owner's operation lock."""
    node = await prepare_user(user_id, email)
    if node is None:
        return await litellm.generate_key(user_id, email, team_id, **options)
    if not {"initial_spend", "key_alias"}.intersection(options) and await litellm.list_user_keys(user_id):
        raise HTTPException(status_code=409, detail="This user already has a key; regenerate it instead")
    result = await upstream.generate_key(user_id, email, node.team_id, **{**options, "max_budget": node.per_user, "budget_duration": node.duration})
    try:
        async with lock_for("team", node.team_id):
            await key_policy.normalize_individual_caps(node, user_id)
    except BaseException:
        await key_cleanup.revoke_created_key(result["key"])
        raise
    return result


async def rotate_key(user_id: str, email: str, team_id: str | None, *, key_alias: str) -> dict:
    """Serialize the spend snapshot, replacement, and old-key revocation together."""
    from app.services import key_budgets

    async with lock_for("user", user_id):
        existing = await litellm.list_user_keys(user_id)
        renamed_key = None
        try:
            for key_info in existing:
                token = key_info.get("token") or key_info.get("api_key") or key_info.get("key")
                if token and key_info.get("key_alias") == key_alias:
                    # Free the unique alias while retaining the live old credential.
                    renamed_key = token
                    await litellm.update_key(token, {"key_alias": f"litegate-rotation-{token_hex(16)}"})
                    break
            result = await _generate_key(user_id, email, team_id, initial_spend=litellm.total_key_spend(existing), key_alias=key_alias)
            try:
                await key_budgets.preserve_rotation_budget(user_id, existing, result["key"])
                for key_info in existing:
                    token = key_info.get("token") or key_info.get("api_key") or key_info.get("key")
                    if token:
                        await litellm.delete_key(token)
                        if token == renamed_key:
                            renamed_key = None
            except BaseException:
                await key_cleanup.revoke_created_key(result["key"])
                raise
        finally:
            if renamed_key:
                await litellm.update_key(renamed_key, {"key_alias": key_alias})
        return result


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
                async with lock_for("team", root.team_id):
                    await upstream.sync_root(root)
                ready.add(root.team_id)
            except HTTPException as exc:
                _logger.warning("Organization root %s synchronization failed: %s", root.team_id, exc.detail)

    await asyncio.gather(*(prepare_root(root) for root in settings.organization_hierarchy.nodes.values()))

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

    async def finish_team(node):
        async with semaphore, lock_for("team", node.team_id):
            if node.team_id in ready:
                try:
                    await key_policy.finish_team(node)
                except HTTPException as exc:
                    _logger.warning("Organization team %s migration pending: %s", node.team_id, exc.detail)

    await asyncio.gather(*(finish_team(node) for node in settings.organization_hierarchy.nodes.values()))


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


async def guard_key(key: str, changes: dict, *, use_key_budget_only: bool = False) -> None:
    if not settings.organization_hierarchy.levels or (
        not use_key_budget_only and not {"team_id", "max_budget", "budget_duration"}.intersection(changes)
    ):
        return
    info = await litellm.get_key_info(key)
    if not info:
        raise HTTPException(status_code=404, detail="Key not found")
    identity = await asyncio.to_thread(store.get, info.get("user_id") or "")
    configured = resolve(info.get("user_id") or "", identity["groups"] if identity else []) if use_key_budget_only else None
    if (
        settings.organization_hierarchy.is_managed_team(info.get("team_id"))
        or settings.organization_hierarchy.is_managed_team(changes.get("team_id"))
        or (identity and identity.get("team_id"))
        or (use_key_budget_only and (identity or configured))
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
    root = next((root for root in settings.organization_hierarchy.nodes.values() if root.team_id == team_id), None)
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
        if not keys or any("max_budget" not in key or "budget_duration" not in key for key in keys):
            raise HTTPException(status_code=502, detail="The key's current allowance is unavailable")
        actual = {"per_user": keys[0]["max_budget"], "duration": keys[0]["budget_duration"], "spend": litellm.total_key_spend(keys)}
        result.update(actual, budget_available=True)
        if valid and any(not key_policy.matches(key, node) for key in keys):
            result["sync_error"] = result["sync_error"] or "Your enforced allowance differs from organizationHierarchy; contact an administrator"
    except HTTPException as exc:
        result["sync_error"] = result["sync_error"] or str(exc.detail)
    return result
