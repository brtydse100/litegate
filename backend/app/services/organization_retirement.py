"""Durable creation evidence and conservative removed-team retirement assessment."""

import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.services import audit, local_users, organization_client as upstream, organization_store


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


def configured_team_ids() -> set[str]:
    references = {node.team_id for node in settings.organization_hierarchy.nodes.values()}
    references.update(team for teams in settings.organization_access_designations.values() for team in teams)
    references.update(settings.organization_group_admins)
    for teams in settings.oidc_group_team_mapping.values():
        references.update([teams] if isinstance(teams, str) else teams)
    references.update(team for team in (settings.sso_default_team_id, settings.key_team_id) if team)
    return references


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
    # /team/delete accepts IDs only. A check followed by deletion can race any
    # external member/key addition, so an empty snapshot never authorizes delete.
    return "atomic_delete_unavailable"


async def assess_removed_teams() -> list[dict]:
    """Audit candidates; no automatic deletion without a verified conditional API."""
    if not settings.organization_cleanup_enabled:
        return []
    results = []
    configured = configured_team_ids()
    candidates = set()
    for team_id in await asyncio.to_thread(owned_teams):
        if team_id in configured:
            continue
        candidates.add(team_id)
        reason = await retirement_reason(team_id)
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
