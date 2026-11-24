"""Durable creation evidence, stale-membership removal and removed-team retirement."""

import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.services import audit, litellm, local_users, organization_store
from app.services import organization_client as upstream

# Last reason audited per team. The periodic reconciler would otherwise record
# an identical event every pass. Production is single-replica, so process-local
# state suffices; a restart re-reports each candidate once.
_reported: dict[str, str] = {}


def mark_created(team_id: str) -> None:
    """Call only after this installation's create operation is confirmed."""
    with local_users.connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO organization_owned_teams(team_id, created_at) VALUES (?, ?)", (team_id, datetime.now(timezone.utc).isoformat())
        )


def owned_teams() -> list[str]:
    with local_users.connect() as db:
        return [row[0] for row in db.execute("SELECT team_id FROM organization_owned_teams ORDER BY team_id")]


def external_team_ids() -> set[str]:
    """Teams referenced by configuration other than the organization hierarchy."""
    references = {team for teams in settings.organization_access_designations.values() for team in teams}
    references.update(settings.organization_group_admins)
    for teams in settings.oidc_group_team_mapping.values():
        references.update([teams] if isinstance(teams, str) else teams)
    references.update(team for team in (settings.sso_default_team_id, settings.key_team_id) if team)
    return references


def configured_team_ids() -> set[str]:
    return {node.team_id for node in settings.organization_hierarchy.nodes.values()} | external_team_ids()


def managed_team_ids() -> set[str]:
    """Teams LiteGate created or adopted by name: the only ones cleanup may change."""
    from app.services import organization_bindings

    return set(owned_teams()) | organization_bindings.bound_team_ids()


def _members(info: dict) -> set[str]:
    team = info.get("team_info") if isinstance(info.get("team_info"), dict) else {}
    rows = [*(team.get("members_with_roles") or []), *(info.get("team_memberships") or [])]
    return {row["user_id"] for row in rows if isinstance(row, dict) and isinstance(row.get("user_id"), str)}


async def retirement_reason(team_id: str) -> str:
    if team_id in configured_team_ids():
        return "configured_reference"
    identities = await asyncio.to_thread(organization_store.list_identities)
    if any(identity.get("team_id") == team_id for identity in identities):
        return "local_identity_reference"
    try:
        info = await upstream.team_info(team_id)
    except HTTPException:
        return "remote_check_unavailable"
    team = info.get("team_info")
    if not isinstance(team, dict) or team.get("team_id") != team_id:
        return "remote_check_incomplete"
    members, memberships, keys = team.get("members_with_roles"), info.get("team_memberships"), info.get("keys")
    if any(isinstance(rows, list) and rows for rows in (members, memberships)):
        return "members_present"
    if isinstance(keys, list) and keys:
        return "keys_present"
    if members != [] or memberships != [] or keys != [] or type(info.get("total_keys")) is not int or info["total_keys"] != 0:
        return "remote_check_incomplete"
    return "empty"


async def _remove_member(team_id: str, user_id: str, reason: str) -> None:
    await litellm.remove_team_member(team_id, user_id)
    await asyncio.to_thread(
        audit.record,
        actor_id="system:organization",
        actor_email="",
        action="organization.membership_removed",
        target=user_id,
        details={"team_id": team_id, "reason": reason},
    )


async def remove_stale_memberships(user_id: str, node) -> None:
    """After a move, leave managed teams outside the member's current path."""
    if not settings.organization_cleanup_enabled:
        return
    nodes = settings.organization_hierarchy.nodes.values()
    keep = {ancestor.team_id for ancestor in nodes if node.path[: len(ancestor.path)] == ancestor.path}
    managed = {item.team_id for item in nodes} | await asyncio.to_thread(managed_team_ids)
    stale = managed - keep - external_team_ids()
    for team_id in await litellm.list_user_team_ids(user_id):
        if team_id in stale:
            await _remove_member(team_id, user_id, "moved")


async def _release_moved_members(team_id: str) -> None:
    """Remove members whose synchronized group now lives in another team."""
    try:
        info = await upstream.team_info(team_id)
    except HTTPException:
        return
    for user_id in sorted(_members(info)):
        identity = await asyncio.to_thread(organization_store.get, user_id)
        if identity and identity.get("team_id") and identity["team_id"] != team_id and not identity.get("sync_error"):
            await _remove_member(team_id, user_id, "team_removed")


def _forget(team_id: str) -> None:
    with local_users.connect() as db:
        db.execute("DELETE FROM organization_owned_teams WHERE team_id=?", (team_id,))
        db.execute("DELETE FROM organization_team_bindings WHERE team_id=?", (team_id,))


async def _delete(team_id: str) -> None:
    await litellm.delete_team(team_id)
    await asyncio.to_thread(_forget, team_id)
    await asyncio.to_thread(
        audit.record,
        actor_id="system:organization",
        actor_email="",
        action="organization.team_deleted",
        target=team_id,
        details={"reason": "removed_from_organization"},
    )


async def retire_removed_teams() -> list[dict]:
    """Empty and delete managed teams that are no longer configured.

    Members who already moved to their new group are removed, and the team is
    deleted only when a fresh read shows no members and no keys. Anything else
    stays and is audited for review. Without any configured groups nothing is
    deleted, so an empty or unreadable hierarchy cannot remove every team.
    """
    if not settings.organization_cleanup_enabled:
        return []
    results = []
    configured = configured_team_ids()
    deletion = bool(settings.organization_hierarchy.levels)
    candidates = set()
    for team_id in sorted(await asyncio.to_thread(managed_team_ids)):
        if team_id in configured:
            continue
        candidates.add(team_id)
        if deletion and await retirement_reason(team_id) == "members_present":
            await _release_moved_members(team_id)
        reason = await retirement_reason(team_id)
        if deletion and reason == "empty":
            await _delete(team_id)
            _reported.pop(team_id, None)
            results.append({"team_id": team_id, "status": "deleted"})
            continue
        result = {"team_id": team_id, "status": "review_required", "reason": reason}
        results.append(result)
        if _reported.get(team_id) == reason:
            continue
        _reported[team_id] = reason
        await asyncio.to_thread(
            audit.record,
            actor_id="system:organization",
            actor_email="",
            action="organization.retirement",
            target=team_id,
            outcome="success",
            details=result,
        )
    # Forget teams that were reconfigured or removed so a recurrence is audited.
    for team_id in set(_reported) - candidates:
        del _reported[team_id]
    return results
