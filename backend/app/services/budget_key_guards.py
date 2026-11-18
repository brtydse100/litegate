"""Fail closed where key mutations would discard aggregate budget accounting."""

import asyncio

from fastapi import HTTPException

from app.config import settings
from app.organization import MembershipConflict
from app.services import litellm, organization_store


def guard_single_key(existing: list[dict]) -> None:
    """Call for a managed owner before applying an enforced per-user share."""
    if settings.hierarchical_budgets_enforced and len(existing) > 1:
        raise HTTPException(409, "Multiple keys require aggregate budget accounting; existing controls were preserved")


def guard_new_key(existing: list[dict]) -> None:
    """Until atomic aggregate accounting exists, never overlap managed keys."""
    if settings.hierarchical_budgets_enforced and existing:
        raise HTTPException(409, "An enforced budget supports one key; additional keys and overlapping rotation require aggregate accounting")


async def guard_rotation(user_id: str, existing: list[dict]) -> None:
    """A managed member replaces their one key, into a team LiteGate can resolve."""
    tree = settings.organization_hierarchy
    if not any(tree.is_managed_team(key.get("team_id")) for key in existing):
        return
    guard_single_key(existing)
    if await asyncio.to_thread(organization_store.get, user_id) is not None:
        return
    try:
        configured = tree.resolve(user_id, [])
    except MembershipConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if configured is None:
        # Group memberships arrive with sign-in (lost with a non-persistent database).
        raise HTTPException(409, "Sign out and sign in again before replacing your key")


async def guard_erase_key(key: str, info: dict | None = None) -> None:
    """Reject deletion/reset while consumed spend lives on a managed key."""
    if not settings.hierarchical_budgets_enforced:
        return
    info = info if info is not None else await litellm.get_key_info(key)
    if not info:
        raise HTTPException(404, "Key not found")
    tree = settings.organization_hierarchy
    owner = info.get("user_id")
    identity = await asyncio.to_thread(organization_store.get, owner) if owner else None
    if tree.is_managed_team(info.get("team_id")) or (identity and tree.is_managed_team(identity.get("team_id"))):
        raise HTTPException(409, "Enforced organization budgets require retained spend; key deletion and spend reset are unavailable")
    if not owner:
        raise HTTPException(502, "Cannot verify key ownership for organization budget accounting")
    try:
        if identity:
            node = tree.resolve(owner, identity["groups"], email=identity["email"], source=identity["auth_source"])
        else:
            node = tree.resolve(owner, [])
    except MembershipConflict as exc:
        raise HTTPException(409, "Cannot verify organization budget accounting") from exc
    if node:
        raise HTTPException(409, "Enforced organization budgets require retained spend; key deletion and spend reset are unavailable")
