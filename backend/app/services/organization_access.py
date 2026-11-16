"""Resolve configured designations against live native team administration."""

import asyncio
from dataclasses import dataclass
from time import monotonic

from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationNode
from app.routers.api_actor import ApiActor
from app.services import organization_client as upstream


@dataclass(frozen=True)
class OrganizationScope:
    global_admin: bool = False
    roots: tuple[str, ...] = ()

    @property
    def first_level(self) -> int:
        tree = settings.organization_hierarchy
        return 0 if self.global_admin else min((tree.nodes[root].level for root in self.roots if root in tree.nodes), default=0)

    def levels(self) -> list[str]:
        return [level.name for level in settings.organization_hierarchy.levels[self.first_level :]]

    def root_for(self, node: OrganizationNode) -> OrganizationNode | None:
        tree = settings.organization_hierarchy
        return next(
            (tree.nodes[root] for root in self.roots if root in tree.nodes and node.path[: len(tree.nodes[root].path)] == tree.nodes[root].path), None
        )

    def allows(self, node: OrganizationNode) -> bool:
        return self.global_admin or self.root_for(node) is not None

    def path(self, node: OrganizationNode) -> list[str]:
        root = self.root_for(node)
        return list(node.path if self.global_admin or root is None else node.path[root.level :])

    def metadata(self, node: OrganizationNode) -> dict:
        tree = settings.organization_hierarchy
        source = tree.nodes.get(node.budget_source)
        return {
            "path": self.path(node),
            "parent_id": node.parent_id if node.parent_id in tree.nodes and self.allows(tree.nodes[node.parent_id]) else None,
            "budget_source": node.budget_source if source is not None and self.allows(source) else None,
            "level": node.level - self.first_level,
        }


GLOBAL_SCOPE = OrganizationScope(global_admin=True)


# Organization pages fan out several requests and poll access every minute.
# Cache each team's native admin IDs briefly. Revocation takes effect within
# ADMIN_TTL; during an upstream outage the last good answer serves for STALE_TTL.
ADMIN_TTL = 30.0
STALE_TTL = 300.0
_admin_cache: dict[str, tuple[float, frozenset[str]]] = {}


async def _team_admins(team_id: str) -> frozenset[str]:
    cached = _admin_cache.get(team_id)
    if cached and monotonic() - cached[0] < ADMIN_TTL:
        return cached[1]
    try:
        info = await upstream.team_info(team_id)
        team = info.get("team_info")
        if not isinstance(team, dict) or team.get("team_id", team_id) != team_id or not isinstance(team.get("members_with_roles"), list):
            raise ValueError("Incomplete team information")
    except (HTTPException, ValueError, AttributeError):
        if cached and monotonic() - cached[0] < STALE_TTL:
            return cached[1]
        return frozenset()
    admins = frozenset(
        member["user_id"]
        for member in team["members_with_roles"]
        if isinstance(member, dict) and isinstance(member.get("user_id"), str) and member.get("role") == "admin"
    )
    _admin_cache[team_id] = (monotonic(), admins)
    return admins


async def resolve_scope(actor: ApiActor) -> OrganizationScope:
    """Designations contain canonical user IDs mapped to configured native TEAM IDs."""
    if actor.proof_key or actor.user.auth_source == "litellm_key":
        raise HTTPException(403, "Portal organization access required")
    if actor.is_admin:
        return GLOBAL_SCOPE
    designated = set(settings.organization_access_designations.get(actor.user.user_id, []))
    authorized, remote = [], []
    for node in settings.organization_hierarchy.nodes.values():
        if node.team_id not in designated:
            continue
        # LiteGate's own scoped administrators do not require an upstream license.
        # These operator-controlled roles grant only organization capabilities;
        # they never promote the identity to a global or native LiteLLM admin.
        if actor.user.user_id in settings.organization_group_admins.get(node.team_id, []):
            authorized.append(node)
            continue
        remote.append(node)
    admins = await asyncio.gather(*(_team_admins(node.team_id) for node in remote))
    authorized += [node for node, ids in zip(remote, admins) if actor.user.user_id in ids]
    roots = tuple(
        node.id for node in authorized if not any(other.id != node.id and node.path[: len(other.path)] == other.path for other in authorized)
    )
    if not roots:
        raise HTTPException(403, "Organization access required")
    return OrganizationScope(roots=roots)


async def capabilities(actor: ApiActor) -> dict:
    try:
        scope = await resolve_scope(actor)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        return {"organization": False, "global_admin": False, "roots": []}
    roots = settings.organization_hierarchy.roots if scope.global_admin else [settings.organization_hierarchy.nodes[root] for root in scope.roots]
    return {"organization": True, "global_admin": scope.global_admin, "roots": [root.id for root in roots]}
