"""Large organizations: scoped budget passes, cached reads and per-user limits."""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.config import settings
from app.main import app
from app.models import CurrentUser
from app.organization import OrganizationHierarchy
from app.routers import budgets
from app.routers.api_actor import ApiActor, get_api_actor
from app.routers.team_policy_context import decorate_team
from app.services import budget_pass, litellm, litellm_client, organization_client as upstream, organization_limits
from app.services import audit, organization_reports as reports, organization_store as store, organization_sync as sync
from tests.test_budget_enforcement import join, org  # noqa: F401 - fixture


def key(user, team):
    return {"token": f"key-{user}", "user_id": user, "team_id": team, "spend": 0, "max_budget": 0}


@pytest.fixture
def reads(monkeypatch):
    """Record whose keys a pass reads; ann, ben and cat are in eng, dan in sales."""
    teams = {"ann": "eng", "ben": "eng", "cat": "eng", "dan": "sales"}
    seen = []

    async def keys(user):
        seen.append(user)
        return [key(user, teams[user])] if user in teams else []

    monkeypatch.setattr(litellm, "list_user_keys", keys)
    monkeypatch.setattr(litellm, "update_key", AsyncMock())
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value=None))
    return teams, seen


@pytest.mark.asyncio
async def test_an_operation_reads_only_the_members_of_its_groups(org, reads, monkeypatch):
    org()
    join("ann", "ben", "cat", "dan")
    teams, seen = reads
    budget_pass.mark_clean(budget_pass.generation())

    @budget_pass.serialized
    async def operation(user_id):
        return user_id

    assert await operation("dan") == "dan"
    assert set(seen) == {"dan"}
    # After money moves between groups every member is read again first.
    seen.clear()
    budget_pass.mark_cross_group_edit()
    await operation("dan")
    assert set(seen) == set(teams)


@pytest.mark.asyncio
async def test_a_key_left_in_another_group_brings_that_group_into_the_pass(org, reads, monkeypatch):
    org()
    join("ann", "ben", "cat", "dan")
    teams, seen = reads
    teams["dan"] = "eng"  # dan's key still sits in Engineering
    budget_pass.mark_clean(budget_pass.generation())

    @budget_pass.serialized
    async def operation(user_id):
        return user_id

    await operation("dan")
    assert {"ann", "ben", "cat", "dan"} <= set(seen)


@pytest.mark.asyncio
async def test_groups_run_in_parallel_but_one_group_runs_one_operation_at_a_time(org, reads):
    org()
    join("ann", "ben", "cat", "dan")
    budget_pass.mark_clean(budget_pass.generation())
    inside, release, order = asyncio.Event(), asyncio.Event(), []

    @budget_pass.serialized
    async def operation(user_id):
        order.append(user_id)
        if user_id == "ann":
            inside.set()
            await release.wait()
        return user_id

    first = asyncio.create_task(operation("ann"))
    await asyncio.wait_for(inside.wait(), 2)
    # Sales is independent of Engineering and finishes while ann's pass is open.
    assert await asyncio.wait_for(operation("dan"), 2) == "dan"
    same_group = asyncio.create_task(operation("ben"))
    await asyncio.sleep(0.05)
    assert "ben" not in order
    release.set()
    await asyncio.wait_for(asyncio.gather(first, same_group), 2)
    assert order == ["ann", "dan", "ben"]


@pytest.mark.asyncio
async def test_a_returning_member_signs_in_without_a_budget_pass(org, monkeypatch):
    org()
    join("ann", "ben")
    node = sync.resolve_identity(store.get("ann"))
    store.synced("ann", node.team_id, sync.policy(node))
    slow = AsyncMock(return_value=node)
    monkeypatch.setattr(sync, "_synchronize_user", slow)
    assert (await sync.synchronize_user("ann")).id == node.id
    slow.assert_not_awaited()
    # A new participant changes ann's share, so the next sign-in applies it.
    join("cat")
    await sync.synchronize_user("ann")
    slow.assert_awaited_once_with("ann")


@pytest.mark.asyncio
async def test_team_reads_are_shared_within_a_step_until_something_is_written(monkeypatch):
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"team_info": {"team_id": "eng"}})

    pooled = httpx.AsyncClient(transport=httpx.MockTransport(handle), event_hooks={"request": [litellm_client._forget_on_write]})
    monkeypatch.setattr(litellm_client, "_shared_client", pooled)
    try:
        with litellm_client.team_cache():
            await upstream.team_info("eng")
            await upstream.team_info("eng")
            await upstream.request("POST", "/team/member_update", payload={})
            await upstream.team_info("eng")
        await upstream.team_info("eng")
    finally:
        await pooled.aclose()
    assert [call for call in calls if call[1] == "/team/info"] == [("GET", "/team/info")] * 3


@pytest.mark.asyncio
async def test_overview_reuses_team_status_for_a_minute(org, monkeypatch):
    org()
    info = AsyncMock(return_value={"team_info": {"max_budget": None, "budget_duration": None, "spend": 2}})
    monkeypatch.setattr(upstream, "team_info", info)
    await reports.overview()
    await reports.overview()
    assert info.await_count == len(settings.organization_hierarchy.nodes)


def nested() -> OrganizationHierarchy:
    return OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Division",
                    "groups": [{"members": [{"name": "Engineering", "litellmTeamId": "eng", "budget": {"perUser": 50, "groupTotal": 500}}]}],
                },
                {
                    "name": "Team",
                    "groups": [{"parent": "Engineering", "members": [{"name": "Apps", "litellmTeamId": "apps", "userIds": ["alice"]}]}],
                },
            ]
        }
    )


@pytest.fixture
def limits(monkeypatch):
    tree = nested()
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "hierarchical_budgets_enabled", True)
    monkeypatch.setattr(settings, "hierarchical_budgets_enforced", False)
    monkeypatch.setattr(budgets.native, "capabilities", AsyncMock(return_value={"supported": False, "version": None, "reasons": []}))
    monkeypatch.setattr(organization_limits, "_base", None)
    monkeypatch.setattr(organization_limits, "_effective", None)
    monkeypatch.setattr(organization_limits, "_applied", {})
    store.remember("alice", "alice@example.invalid", "explicit", [])
    ids = {node.team_id: node.id for node in tree.nodes.values()}
    actor = {"value": ApiActor(CurrentUser(user_id="root", email="root@example.invalid", role="admin", auth_source="sso"))}
    app.dependency_overrides[get_api_actor] = lambda: actor["value"]
    yield ids, actor
    app.dependency_overrides.pop(get_api_actor, None)


def per_user(user="alice"):
    return sync.resolve_identity(store.get(user)).per_user


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_a_per_user_limit_overrides_configuration_and_is_inherited(limits):
    ids, _ = limits
    assert per_user() == 50
    async with client() as http:
        parent = await http.patch(f"/api/v1/organization/groups/{ids['eng']}/per-user", json={"amount": "30"})
        assert parent.json() == {"node_id": ids["eng"], "per_user": 30, "per_user_config": 50, "per_user_override": 30}
        assert per_user() == 30  # Apps inherits its parent's limit
        await http.patch(f"/api/v1/organization/groups/{ids['apps']}/per-user", json={"amount": 10})
        assert per_user() == 10
        view = (await http.get("/api/v1/organization/budgets")).json()
        apps = next(group for group in view["groups"] if group["id"] == ids["apps"])
        assert (apps["per_user"], apps["per_user_config"], apps["per_user_override"], apps["can_edit_per_user"]) == (10, 50, 10, True)
        await http.patch(f"/api/v1/organization/groups/{ids['apps']}/per-user", json={"amount": None})
        await http.patch(f"/api/v1/organization/groups/{ids['eng']}/per-user", json={"amount": None})
    assert per_user() == 50
    assert organization_limits.base().nodes[ids["eng"]].per_user == 50


@pytest.mark.asyncio
async def test_a_per_user_limit_edit_wakes_the_organization_sweep(limits, monkeypatch):
    ids, _ = limits
    wake = Mock()
    monkeypatch.setattr(sync, "request_reconciliation", wake)
    async with client() as http:
        await http.patch(f"/api/v1/organization/groups/{ids['eng']}/per-user", json={"amount": "30"})
        await http.patch(f"/api/v1/organization/groups/{ids['eng']}/per-user", json={"amount": None})
    assert wake.call_count == 2


@pytest.mark.asyncio
async def test_the_limit_survives_a_restart_and_shows_on_the_teams_page(limits, monkeypatch):
    ids, _ = limits
    organization_limits.save(ids["apps"], 12_000_000)
    # A restart rebuilds the configuration, then applies the stored override.
    monkeypatch.setattr(settings, "organization_hierarchy", nested())
    assert per_user() == 50
    organization_limits.apply()
    assert per_user() == 12
    team = decorate_team({"team_id": "apps"})
    assert (team["organization_node_id"], team["organization_per_user"], team["organization_per_user_override"]) == (ids["apps"], 12, 12)


@pytest.mark.asyncio
async def test_only_a_global_administrator_changes_per_user_limits(limits, monkeypatch):
    ids, actor = limits
    actor["value"] = ApiActor(CurrentUser(user_id="manager", email="manager@example.invalid", role="user", auth_source="sso"))
    monkeypatch.setattr(settings, "organization_access_designations", {"manager": ["eng"]})
    monkeypatch.setattr(settings, "organization_group_admins", {"eng": ["manager"]})
    async with client() as http:
        denied = await http.patch(f"/api/v1/organization/groups/{ids['apps']}/per-user", json={"amount": "999"})
        assert denied.status_code == 403
        view = (await http.get("/api/v1/organization/budgets")).json()
    assert all(group["can_edit_per_user"] is False for group in view["groups"])
    assert per_user() == 50


@pytest.mark.asyncio
async def test_per_user_limit_changes_are_validated_and_audited(limits):
    ids, _ = limits
    async with client() as http:
        assert (await http.patch(f"/api/v1/organization/groups/{ids['apps']}/per-user", json={"amount": "-1"})).status_code == 422
        assert (await http.patch("/api/v1/organization/groups/missing/per-user", json={"amount": "5"})).status_code == 404
        assert (await http.patch(f"/api/v1/organization/groups/{ids['apps']}/per-user", json={"amount": "5"})).status_code == 200
    assert any(event["action"] == "organization.per_user_limit" for event in audit.list_events(limit=5))
