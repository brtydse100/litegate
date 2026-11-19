"""Reconcile Helm-managed policy without resetting LiteLLM's spend counters."""

import asyncio
import logging
from secrets import token_hex
from weakref import WeakValueDictionary

from fastapi import HTTPException

from app.config import settings

from app.organization import MembershipConflict, OrganizationNode
from app.services import audit, budget_enforcement, key_cleanup, key_spend, litellm, organization_key_policy as key_policy
from app.services import budget_key_guards, budget_pass, key_rotation_freeze
from app.services import organization_client as upstream, organization_store as store
from app.services import organization_discovery as discovery  # noqa: F401 - used by organization_reconcile and tests

_logger = logging.getLogger(__name__)
_locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = WeakValueDictionary()


def lock_for(kind: str, identifier: str) -> asyncio.Lock:
    key = (kind, identifier)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def resolve(user_id: str, groups: list[str], *, email: str = "", source: str = "") -> OrganizationNode | None:
    try:
        return settings.organization_hierarchy.resolve(user_id, groups, email=email, source=source)
    except MembershipConflict as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def resolve_identity(identity: dict) -> OrganizationNode | None:
    if identity["auth_source"] == "configured_email" and identity.get("sync_error"):
        raise HTTPException(status_code=409, detail=identity["sync_error"])
    node = resolve(identity["user_id"], identity["groups"], email=identity["email"], source=identity["auth_source"])
    return budget_enforcement.allowance(node, identity["user_id"]) if node else node


def policy(node: OrganizationNode) -> dict:
    return {"node_id": node.id, "per_user": node.per_user, "duration": node.duration}


async def record_identity(user_id: str, email: str, source: str, groups: list[str]) -> OrganizationNode | None:
    """Persist verified claims even when they invalidate an existing membership."""
    if not settings.organization_hierarchy.levels:
        return None
    email = email.strip().casefold() if source == "sso" else email
    async with lock_for("user", user_id):
        previous = await asyncio.to_thread(store.get, user_id)
        try:
            node = resolve(user_id, groups, email=email, source=source)
            if node is not None or previous:
                await asyncio.to_thread(store.remember, user_id, email, source, groups)
            if node is not None:
                await asyncio.to_thread(budget_enforcement.mark_participant, user_id)
            # A changed group or a new participant must reach the shares used
            # by the immediate synchronization below.
            await budget_enforcement.refresh_async()
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


def settled(identity: dict) -> OrganizationNode | None:
    """The member's group when the last synchronization already applied it."""
    if identity.get("sync_error"):
        return None
    try:
        node = resolve_identity(identity)
    except HTTPException:
        return None
    if node is None or identity.get("team_id") != node.team_id or identity.get("policy") != policy(node):
        return None
    return node


async def synchronize_user(user_id: str) -> OrganizationNode | None:
    """Finish provisioning from current stored claims without rewriting them."""
    if not settings.organization_hierarchy.levels:
        return None
    identity = await asyncio.to_thread(store.get, user_id)
    # A returning member whose group, share and team are unchanged needs no
    # budget pass; the minute-by-minute synchronization keeps them current.
    node = settled(identity) if identity else None
    return node or await _synchronize_user(user_id)


@budget_pass.serialized
async def _synchronize_user(user_id: str) -> OrganizationNode | None:
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
        node = resolve_identity(identity)
        if node is None:
            raise HTTPException(status_code=403, detail="Your organization mapping is no longer valid")
        return await sync_identity(identity, await sync_root(node))
    except HTTPException as exc:
        await asyncio.to_thread(store.failed, identity["user_id"], str(exc.detail))
        raise


async def sync_identity(identity: dict, info: dict, *, defer_finalization: bool = False) -> OrganizationNode:
    existing = await key_rotation_freeze.recover(identity["user_id"], await budget_pass.keys(identity["user_id"]))
    budget_key_guards.guard_single_key(existing)
    await budget_enforcement.observe(identity["user_id"], existing)
    node = resolve_identity(identity)
    if node is None:
        raise HTTPException(status_code=409, detail="Organization mapping was removed; review the user's keys before changing membership")
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
    if not defer_finalization:
        await finalize_identity(identity, node, existing)
    return node


async def finalize_identity(identity: dict, node: OrganizationNode, keys: list[dict]) -> None:
    if keys:
        async with lock_for("team", node.team_id):
            await key_policy.normalize_individual_caps(node, identity["user_id"], keys)
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
    await budget_enforcement.refresh_async()
    node = resolve_identity(identity)
    if node is None:
        raise HTTPException(status_code=403, detail="Your organization mapping is no longer valid")
    return await synchronize(identity)


@budget_pass.serialized(provision=True)
async def generate_key(user_id: str, email: str, team_id: str | None, **options) -> dict:
    async with lock_for("user", user_id):
        return await _generate_key(user_id, email, team_id, **options)


async def _generate_key(user_id: str, email: str, team_id: str | None, *, replacing: bool = False, **options) -> dict:
    await asyncio.to_thread(budget_enforcement.mark_participant, user_id)
    node = await prepare_user(user_id, email)
    if node is None:
        return await litellm.generate_key(user_id, email, team_id, **options)
    if not replacing:
        budget_key_guards.guard_new_key(await litellm.list_user_keys(user_id))
    identity = await asyncio.to_thread(store.get, user_id)
    if identity and identity["auth_source"] == "sso":
        email = identity["email"].strip().casefold()
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
    """Replace keys; under enforced budgets, pause the old key until its spend settles."""
    if not budget_enforcement.enforced():
        return await _rotate_key(user_id, email, team_id, key_alias=key_alias)
    if user_id in key_rotation_freeze.active:
        raise HTTPException(status_code=409, detail="A key replacement is already in progress")
    key_rotation_freeze.active.add(user_id)
    try:
        async with lock_for("user", user_id):
            existing = await key_spend.current_keys(user_id)
            await budget_key_guards.guard_rotation(user_id, existing)
            froze = await key_rotation_freeze.freeze(user_id, existing)
        try:
            if froze:
                # Outside every lock: other members keep working meanwhile.
                await key_rotation_freeze.settle()
            return await _rotate_key(user_id, email, team_id, key_alias=key_alias)
        except BaseException:
            if froze:
                async with lock_for("user", user_id):
                    await key_rotation_freeze.thaw(user_id)
            raise
    finally:
        key_rotation_freeze.active.discard(user_id)


@budget_pass.serialized
async def _rotate_key(user_id: str, email: str, team_id: str | None, *, key_alias: str) -> dict:
    """Serialize the spend snapshot, replacement, and old-key revocation together."""
    from app.services import key_budgets, key_rotation_policy

    async with lock_for("user", user_id):
        existing = await key_spend.current_keys(user_id)
        await budget_key_guards.guard_rotation(user_id, existing)
        controls = await key_rotation_policy.snapshot(user_id, [key_rotation_freeze.original(key) for key in existing])
        if key_rotation_policy.requires_assistance(existing):
            raise HTTPException(
                status_code=409,
                detail="Keys with per-model budgets or multiple budget windows require administrator-assisted rotation in LiteLLM to preserve usage windows.",
            )
        renamed_key = None
        try:
            for key_info in existing:
                token = key_info.get("token") or key_info.get("api_key") or key_info.get("key")
                if token and key_info.get("key_alias") == key_alias:
                    # Free the unique alias while retaining the live old credential.
                    renamed_key = token
                    await litellm.update_key(token, {"key_alias": f"litegate-rotation-{token_hex(16)}"})
                    break
            result = await _generate_key(
                user_id, email, team_id, replacing=True, initial_spend=litellm.total_key_spend(existing), key_alias=key_alias
            )
            try:
                await key_budgets.preserve_rotation_budget(user_id, existing, result["key"])
                verified = await key_rotation_policy.preserve(user_id, controls, result["key"])
                source = await key_spend.verify_replacement(user_id, existing, result["key"])
                if (
                    key_rotation_policy.requires_assistance(source)
                    or await key_rotation_policy.snapshot(user_id, [key_rotation_freeze.original(key) for key in source]) != controls
                ):
                    raise HTTPException(
                        status_code=409, detail="Source key policy changed during rotation; original keys were kept. Retry the operation."
                    )
                if verified is not None and "expires" in verified:
                    result = {**result, "expires": verified["expires"]}
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
    from app.services import organization_reconcile

    await organization_reconcile.reconcile()


async def reconciliation_attempt() -> bool:
    try:
        await reconcile()
        if settings.organization_cleanup_enabled:
            from app.services import organization_retirement

            await organization_retirement.assess_removed_teams()
        return True
    except Exception:
        _logger.exception("Organization synchronization failed")
        return False


# Set by budget and limit edits so their changes apply without waiting for a sweep.
_wake: asyncio.Event | None = None
MIN_PASS_SPACING = 60


def request_reconciliation() -> None:
    """Run the next organization pass soon (at most once a minute)."""
    if _wake is not None:
        _wake.set()


async def run_reconciliation() -> None:
    """Sweep every ``organization_sync_interval_seconds``, or sooner when woken.

    Passes are at least a minute apart. Sign-ins and key operations already
    synchronize their own user, so the full sweep only repairs drift.
    """
    global _wake
    _wake = asyncio.Event()
    failed = False
    while True:
        await asyncio.sleep(MIN_PASS_SPACING)
        # Until a pass verifies budget state, every sign-in reads the whole
        # installation, so failed or unverified passes retry after the spacing.
        unverified = bool(settings.organization_hierarchy.levels) and budget_pass.cross_group_pending()
        remaining = 0 if failed or unverified else max(0, settings.organization_sync_interval_seconds - MIN_PASS_SPACING)
        try:
            await asyncio.wait_for(_wake.wait(), timeout=remaining)
        except TimeoutError:
            pass
        _wake.clear()
        failed = await reconciliation_attempt() is False


def changes_inherited_allowance(changes: dict) -> bool:
    # Newly discovered budget knobs must not silently bypass the configured
    # allowance. Separate model caps/routing cannot widen the overall key cap.
    return any("budget" in field.lower() and field not in {"model_max_budget", "budget_fallbacks"} for field in changes)


def guard_team(team_id: str, changes: dict | None = None) -> None:
    if settings.organization_hierarchy.is_managed_team(team_id) and (changes is None or changes_inherited_allowance(changes)):
        raise HTTPException(status_code=409, detail="This team's membership and budget are managed by organizationHierarchy")


async def guard_key(key: str, changes: dict, *, use_key_budget_only: bool = False) -> None:
    if any("spend" in field.lower() for field in changes):
        await budget_key_guards.guard_erase_key(key)
    if not settings.organization_hierarchy.levels or (
        not use_key_budget_only and "team_id" not in changes and not changes_inherited_allowance(changes)
    ):
        return
    info = await litellm.get_key_info(key)
    if not info:
        raise HTTPException(status_code=404, detail="Key not found")
    identity = await asyncio.to_thread(store.get, info.get("user_id") or "")
    configured = (resolve_identity(identity) if identity else resolve(info.get("user_id") or "", [])) if use_key_budget_only else None
    if (
        settings.organization_hierarchy.is_managed_team(info.get("team_id"))
        or settings.organization_hierarchy.is_managed_team(changes.get("team_id"))
        or (identity and identity.get("team_id"))
        or (use_key_budget_only and (identity or configured))
    ):
        raise HTTPException(status_code=409, detail="This key's team and budget are managed by organizationHierarchy")
