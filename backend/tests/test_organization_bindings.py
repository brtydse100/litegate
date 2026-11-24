"""Restructured groups reuse their existing LiteLLM team by name, never a duplicate."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, litellm_snapshot, local_users, organization_limits, organization_retirement
from app.services import organization_bindings as bindings
from app.services import organization_client as upstream


def tree(children: dict[str, list[str]]) -> OrganizationHierarchy:
    roots = [{"name": name, "litellmTeamId": name.lower()} for name in children]
    groups = [{"parent": parent, "members": [{"name": name} for name in names]} for parent, names in children.items() if names]
    return OrganizationHierarchy.model_validate(
        {"levels": [{"name": "Division", "groups": [{"members": roots}]}, {"name": "Team", "groups": groups}]}
    )


def node(hierarchy: OrganizationHierarchy, name: str):
    return next(item for item in hierarchy.nodes.values() if item.member.name == name)


def audits(action: str) -> list[str]:
    with local_users.connect() as db:
        return [row[0] for row in db.execute("SELECT details_json FROM audit_events WHERE action=? ORDER BY id", (action,))]


@pytest.fixture
def unresolved(monkeypatch):
    monkeypatch.setattr(bindings, "_resolved", False)

    def listing(teams: dict[str, str]):
        monkeypatch.setattr(
            litellm_snapshot, "load_teams", AsyncMock(return_value={team: {"team_id": team, "team_alias": alias} for team, alias in teams.items()})
        )

    return listing


@pytest.mark.asyncio
async def test_moved_group_reuses_its_team_instead_of_creating_a_duplicate(monkeypatch, unresolved):
    before = tree({"Eng": ["B", "C"], "Ops": []})
    old_team = node(before, "B").team_id
    after = tree({"Eng": ["C"], "Ops": ["B"]})
    monkeypatch.setattr(settings, "organization_hierarchy", after)
    unresolved({"eng": "Eng", "ops": "Ops", old_team: "B", node(after, "C").team_id: "C"})

    await bindings.ensure()

    assert settings.organization_hierarchy.nodes[node(after, "B").id].team_id == old_team
    assert bindings.rows() == {node(after, "B").id: old_team}
    assert len(audits("organization.team_adopted")) == 1
    # A sign-in that reaches team creation now syncs the adopted team instead.
    monkeypatch.setattr(litellm, "get_team", AsyncMock(side_effect=lambda team_id: None if team_id != old_team else {"team_id": old_team}))
    create = AsyncMock()
    monkeypatch.setattr(litellm, "create_team", create)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {}}))
    await upstream.sync_root(node(after, "B"))
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("children", "extra", "reason"),
    [
        ({"Eng": ["B"], "Ops": []}, {"x1": "B", "x2": "B"}, "ambiguous_alias"),
        ({"B": ["B"], "Ops": []}, {"x1": "B"}, "duplicate_group_name"),
    ],
)
async def test_ambiguous_names_create_a_new_team_and_audit_why(monkeypatch, unresolved, children, extra, reason):
    hierarchy = tree(children)
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    unresolved({"eng": "Eng", "ops": "Ops", "b": "B-root", **extra})

    await bindings.ensure()
    await bindings.ensure()  # Resolved once; repeated passes do not repeat audits.

    assert bindings.rows() == {}
    child = next(item for item in hierarchy.nodes.values() if item.member.name == "B" and item.parent_id)
    assert settings.organization_hierarchy.nodes[child.id].team_id.startswith("litegate-org-")
    assert len(audits("organization.team_adoption_skipped")) == 1
    assert reason in audits("organization.team_adoption_skipped")[0]


@pytest.mark.asyncio
async def test_team_already_used_by_configuration_is_never_adopted(monkeypatch, unresolved):
    hierarchy = tree({"Eng": ["B"], "Ops": []})
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    monkeypatch.setattr(settings, "sso_default_team_id", "shared")
    unresolved({"eng": "Eng", "ops": "Ops", "shared": "B"})

    await bindings.ensure()

    assert bindings.rows() == {}
    assert "already_bound" in audits("organization.team_adoption_skipped")[0]


@pytest.mark.asyncio
async def test_explicit_team_id_wins_and_existing_computed_team_is_kept(monkeypatch, unresolved):
    hierarchy = tree({"Eng": ["B", "C"], "Ops": []})
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    unresolved({"eng": "Eng", "ops": "Ops", node(hierarchy, "B").team_id: "B", "other": "C", "dup": "Eng"})

    await bindings.ensure()

    # B's own team exists; Eng has an explicit ID; only C adopts.
    assert bindings.rows() == {node(hierarchy, "C").id: "other"}


@pytest.mark.asyncio
async def test_adoption_survives_restart_and_per_user_limit_overrides(monkeypatch, unresolved):
    hierarchy = tree({"Eng": ["B"], "Ops": []})
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    unresolved({"eng": "Eng", "ops": "Ops", "old-b": "B"})
    await bindings.ensure()

    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)  # A restart reloads configuration.
    bindings.load()
    b = node(hierarchy, "B")
    assert settings.organization_hierarchy.nodes[b.id].team_id == "old-b"
    organization_limits.save(b.id, 1_000_000)
    assert settings.organization_hierarchy.nodes[b.id].team_id == "old-b"
    assert settings.organization_hierarchy.nodes[b.id].per_user == 1


@pytest.mark.asyncio
async def test_no_team_is_created_while_existing_teams_cannot_be_checked(monkeypatch, unresolved):
    hierarchy = tree({"Eng": ["B"], "Ops": []})
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    monkeypatch.setattr(litellm_snapshot, "load_teams", AsyncMock(side_effect=HTTPException(status_code=502, detail="down")))
    monkeypatch.setattr(litellm, "get_team", AsyncMock(return_value=None))
    create = AsyncMock()
    monkeypatch.setattr(litellm, "create_team", create)

    with pytest.raises(HTTPException) as error:
        await upstream.sync_root(node(hierarchy, "B"))

    assert error.value.status_code == 503
    create.assert_not_awaited()
    assert not bindings.resolved()


@pytest.mark.asyncio
async def test_merged_group_members_leave_the_removed_team_before_it_is_deleted(monkeypatch, unresolved):
    """Teams A, B and C; C is deleted and its people move to B."""
    from app.services import organization_store as store

    before = tree({"Org": ["A", "B", "C"]})
    c_team = node(before, "C").team_id
    after = tree({"Org": ["A", "B"]})
    monkeypatch.setattr(settings, "organization_hierarchy", after)
    monkeypatch.setattr(settings, "organization_cleanup_enabled", True)
    unresolved({"org": "Org", node(after, "A").team_id: "A", node(after, "B").team_id: "B", c_team: "C"})
    await bindings.ensure()
    organization_retirement.mark_created(c_team)
    store.remember("carol", "carol@example.com", "explicit", [])
    store.synced("carol", node(after, "B").team_id, {})

    members = [{"user_id": "carol"}]

    async def team_info(team_id):
        return {"team_info": {"team_id": team_id, "members_with_roles": list(members)}, "team_memberships": [], "keys": [], "total_keys": 0}

    async def remove(team_id, user_id):
        members.remove({"user_id": user_id})

    monkeypatch.setattr(upstream, "team_info", team_info)
    monkeypatch.setattr(litellm, "remove_team_member", AsyncMock(side_effect=remove))
    monkeypatch.setattr(litellm, "delete_team", AsyncMock())

    assert await organization_retirement.retire_removed_teams() == [{"team_id": c_team, "status": "deleted"}]
    litellm.remove_team_member.assert_awaited_once_with(c_team, "carol")
    litellm.delete_team.assert_awaited_once_with(c_team)
    assert len(audits("organization.membership_removed")) == 1


@pytest.mark.asyncio
async def test_moving_member_leaves_old_managed_team_but_not_other_teams(monkeypatch):
    hierarchy = tree({"Eng": ["B", "C"], "Ops": []})
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    monkeypatch.setattr(settings, "organization_cleanup_enabled", True)
    monkeypatch.setattr(settings, "sso_default_team_id", "everyone")
    b, c = node(hierarchy, "B"), node(hierarchy, "C")
    monkeypatch.setattr(litellm, "list_user_team_ids", AsyncMock(return_value=["eng", b.team_id, c.team_id, "everyone", "unrelated"]))
    monkeypatch.setattr(litellm, "remove_team_member", AsyncMock())

    await organization_retirement.remove_stale_memberships("dana", c)

    litellm.remove_team_member.assert_awaited_once_with(b.team_id, "dana")
