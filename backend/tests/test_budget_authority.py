"""HTTP budget authority: redistribute assigned funds without changing the total."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import settings
from app.main import app
from app.models import CurrentUser
from app.organization import OrganizationHierarchy
from app.routers import budgets
from app.routers.api_actor import ApiActor, get_api_actor
from app.services import budget_enforcement, budget_store, organization_store


def actor(user_id, *, role="user", source="sso"):
    return ApiActor(CurrentUser(user_id=user_id, email=f"{user_id}@example.invalid", role=role, auth_source=source))


@pytest.fixture
def authority(monkeypatch):
    tree = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Division",
                    "groups": [
                        {
                            "members": [
                                {"name": "Engineering", "litellmTeamId": "eng", "budget": {"groupTotal": 100}},
                                {"name": "Other", "litellmTeamId": "other", "budget": {"groupTotal": 100}},
                            ]
                        }
                    ],
                },
                {
                    "name": "Team",
                    "groups": [
                        {
                            "parent": "Engineering",
                            "members": [
                                {"name": "Apps", "litellmTeamId": "apps", "userIds": ["alice"], "budget": {"groupTotal": 40}},
                                {"name": "Infra", "litellmTeamId": "infra", "userIds": ["bob"], "budget": {"groupTotal": 40}},
                            ],
                        }
                    ],
                },
            ]
        }
    )
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "hierarchical_budgets_enabled", True)
    monkeypatch.setattr(settings, "hierarchical_budgets_enforced", False)
    monkeypatch.setattr(settings, "organization_access_designations", {"manager": ["eng"], "child-manager": ["apps"]})
    monkeypatch.setattr(settings, "organization_group_admins", {"eng": ["manager"], "apps": ["child-manager"]})
    monkeypatch.setattr(budgets.native, "capabilities", AsyncMock(return_value={"supported": False, "version": None, "reasons": []}))
    for user in ("alice", "bob"):
        organization_store.remember(user, f"{user}@example.invalid", "explicit", [])
        budget_enforcement.mark_participant(user)
    context = SimpleNamespace(actor=actor("manager"), nodes={node.team_id: node for node in tree.nodes.values()})
    app.dependency_overrides[get_api_actor] = lambda: context.actor
    yield context
    app.dependency_overrides.pop(get_api_actor, None)


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def group_url(context, team):
    return f"/api/v1/organization/budgets/groups/{context.nodes[team].id}"


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", ["50", "150"])
async def test_team_admin_cannot_change_assigned_total_even_with_direct_api_request(authority, amount):
    async with client() as http:
        result = await http.patch(group_url(authority, "eng"), json={"revision": 0, "amount": amount})
    assert result.status_code == 403
    assert "assigned budget" in result.json()["detail"]
    assert budget_store.read()["revision"] == 0
    assert budget_store.read()["envelopes"] == {}


@pytest.mark.asyncio
async def test_parent_admin_redistributes_existing_total_and_member_overrides(authority):
    async with client() as http:
        reduced = await http.patch(group_url(authority, "apps"), json={"revision": 0, "amount": "20"})
        assert reduced.status_code == 200
        redistributed = await http.patch(group_url(authority, "infra"), json={"revision": 1, "amount": "80"})
        assert redistributed.status_code == 200
        view = {row["id"]: row for row in redistributed.json()["groups"]}
        root = view[authority.nodes["eng"].id]
        assert root["assigned"] == 100 and root["allocated"] == 100
        assert root["can_edit_envelope"] is False
        assert view[authority.nodes["apps"].id]["can_edit_envelope"] is True
        member = await http.patch(group_url(authority, "infra") + "/users/bob", json={"revision": 2, "amount": "60"})
        assert member.status_code == 200
        rejected = await http.patch(group_url(authority, "apps"), json={"revision": 3, "amount": "21"})
        assert rejected.status_code == 409
    assert budget_store.read()["revision"] == 3
    assert authority.nodes["eng"].id not in budget_store.read()["envelopes"]


@pytest.mark.asyncio
async def test_child_admin_needs_parent_authority_to_change_its_envelope(authority):
    authority.actor = actor("child-manager")
    async with client() as http:
        denied = await http.patch(group_url(authority, "apps"), json={"revision": 0, "amount": "50"})
        assert denied.status_code == 403
        member = await http.patch(group_url(authority, "apps") + "/users/alice", json={"revision": 0, "amount": "30"})
        assert member.status_code == 200
        hidden = await http.patch(group_url(authority, "infra"), json={"revision": 1, "amount": "20"})
        assert hidden.status_code == 404
    assert budget_store.read()["envelopes"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("role, source", [("user", "sso"), ("admin", "litellm_key")])
async def test_unqualified_users_and_key_identities_cannot_allocate(authority, role, source):
    authority.actor = actor("ordinary", role=role, source=source)
    async with client() as http:
        result = await http.patch(group_url(authority, "apps"), json={"revision": 0, "amount": "50"})
    assert result.status_code == 403
    assert budget_store.read()["revision"] == 0


@pytest.mark.asyncio
async def test_system_admin_retains_authority_to_assign_total(authority):
    authority.actor = actor("system", role="admin")
    async with client() as http:
        result = await http.patch(group_url(authority, "eng"), json={"revision": 0, "amount": "150"})
    assert result.status_code == 200
    root = next(row for row in result.json()["groups"] if row["id"] == authority.nodes["eng"].id)
    assert root["assigned"] == 150 and root["can_edit_envelope"] is True
