"""Reuse existing LiteLLM teams by name when the organization is restructured.

A group without ``litellmTeamId`` normally uses a team ID derived from its path,
so moving it under another parent would create a second team with the same
name. Before creating a team, LiteGate adopts the one existing LiteLLM team
whose alias equals the group's name, provided the match is unambiguous:
exactly one team has that alias, exactly one configured group has that name,
and no other group or configured reference already uses the team. Adoptions
are stored so later passes and restarts keep the same team.
"""

import asyncio
import json
from datetime import UTC, datetime

from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import audit, litellm_snapshot, local_users, organization_limits

_lock = asyncio.Lock()
_resolved = False
# Last skip reason audited per group, so each pass does not repeat it.
_skipped: dict[str, str] = {}


def rows() -> dict[str, str]:
    with local_users.connect() as db:
        return {row["node_id"]: row["team_id"] for row in db.execute("SELECT node_id, team_id FROM organization_team_bindings")}


def bound_team_ids() -> set[str]:
    return set(rows().values())


def forget(team_id: str) -> None:
    with local_users.connect() as db:
        db.execute("DELETE FROM organization_team_bindings WHERE team_id=?", (team_id,))


def _adopt(node, team_id: str) -> None:
    with local_users.connect() as db:
        # The team may still be recorded for a group that no longer exists.
        db.execute("DELETE FROM organization_team_bindings WHERE team_id=? OR node_id=?", (team_id, node.id))
        db.execute(
            "INSERT INTO organization_team_bindings(node_id, team_id, group_name, path_json, adopted_at) VALUES (?, ?, ?, ?, ?)",
            (node.id, team_id, node.member.name, json.dumps(list(node.path)), datetime.now(UTC).isoformat()),
        )


def usable(hierarchy: OrganizationHierarchy, stored: dict[str, str]) -> dict[str, str]:
    """Bindings that apply to current groups without colliding with configured IDs."""
    explicit = {node.member.litellmTeamId for node in hierarchy.nodes.values() if node.member.litellmTeamId}
    return {
        node_id: team_id
        for node_id, team_id in stored.items()
        if node_id in hierarchy.nodes and not hierarchy.nodes[node_id].member.litellmTeamId and team_id not in explicit
    }


def install(stored: dict[str, str]) -> None:
    configured = organization_limits.base().bound({})
    settings.organization_hierarchy = configured.bound(usable(configured, stored))
    organization_limits.apply()


def load() -> None:
    """Apply stored adoptions at startup, before any synchronization."""
    if settings.organization_hierarchy.levels:
        install(rows())


def resolved() -> bool:
    return _resolved


def _external_references() -> set[str]:
    from app.services import organization_retirement

    return organization_retirement.external_team_ids()


async def ensure() -> None:
    """Adopt same-named teams once per process; retried by each pass until it succeeds."""
    global _resolved
    if _resolved or not settings.organization_hierarchy.levels:
        return
    async with _lock:
        if _resolved:
            return
        teams = await litellm_snapshot.load_teams()
        stored = {node: team for node, team in (await asyncio.to_thread(rows)).items() if team in teams}
        for team_id in bound_team_ids() - set(stored.values()):
            await asyncio.to_thread(forget, team_id)
        hierarchy = organization_limits.base().bound({})
        current = usable(hierarchy, stored)
        hierarchy = hierarchy.bound(current)
        taken = {node.team_id for node in hierarchy.nodes.values()} | _external_references()
        aliases: dict[str, list[str]] = {}
        for team_id, team in teams.items():
            if isinstance(team.get("team_alias"), str):
                aliases.setdefault(team["team_alias"], []).append(team_id)
        names: dict[str, int] = {}
        for node in hierarchy.nodes.values():
            names[node.member.name] = names.get(node.member.name, 0) + 1
        for node in sorted(hierarchy.nodes.values(), key=lambda item: (item.level, item.path)):
            if node.member.litellmTeamId or node.id in current or node.team_id in teams:
                continue
            matches = aliases.get(node.member.name, [])
            if not matches:
                continue
            reason = (
                "ambiguous_alias"
                if len(matches) > 1
                else "duplicate_group_name"
                if names[node.member.name] > 1
                else "already_bound"
                if matches[0] in taken
                else None
            )
            if reason:
                await _audit_skip(node, matches, reason)
                continue
            await asyncio.to_thread(_adopt, node, matches[0])
            current[node.id] = matches[0]
            taken.add(matches[0])
            await asyncio.to_thread(
                audit.record,
                actor_id="system:organization",
                actor_email="",
                action="organization.team_adopted",
                target=matches[0],
                details={"path": list(node.path), "replaces": node.team_id},
            )
        install(current)
        _resolved = True


async def _audit_skip(node, matches: list[str], reason: str) -> None:
    if _skipped.get(node.id) == reason:
        return
    _skipped[node.id] = reason
    await asyncio.to_thread(
        audit.record,
        actor_id="system:organization",
        actor_email="",
        action="organization.team_adoption_skipped",
        target=node.team_id,
        details={"path": list(node.path), "reason": reason, "candidates": matches[:10]},
    )


async def require(node) -> None:
    """Before creating a team, make sure no same-named team should be reused."""
    if node.member.litellmTeamId:
        return
    try:
        await ensure()
    except HTTPException as exc:
        raise HTTPException(status_code=503, detail="Could not check LiteLLM for an existing team to reuse; retrying") from exc
