"""Delegated access is a current capability and never reveals other subtrees."""

from datetime import datetime, timezone
from importlib import import_module, util
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.config import settings
from app.models import CurrentUser
from app.organization import OrganizationHierarchy
from app.routers.api_actor import ApiActor
from app.services import local_users, organization_client as upstream, organization_reports as reports, organization_store as store
from tests.test_organization_config import example


@pytest.fixture
def scoped(monkeypatch, tmp_path):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "scope.db"))
    local_users.init_db()
    root = next(node for node in tree.nodes.values() if node.member.name == "Digital")
    monkeypatch.setitem(settings.__dict__, "organization_access_designations", {"delegate": [root.team_id]})
    store.remember("alice", "alice@example.com", "sso", ["squad1"])
    store.remember("outsider", "outside@example.com", "sso", [])
    store.remember("broken", "broken@example.com", "sso", ["squad1", "squad2"])
    monkeypatch.setattr("app.services.litellm.list_user_keys", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        upstream, "team_info", AsyncMock(return_value={"team_info": {"members_with_roles": [{"user_id": "delegate", "role": "admin"}], "spend": 0}})
    )
    return tree, root, ApiActor(CurrentUser(user_id="delegate", email="delegate@example.com", role="user", auth_source="sso"))


@pytest.mark.asyncio
async def test_litegate_group_admin_works_without_enterprise_and_requires_both_grants(monkeypatch, scoped):
    _, root, actor = scoped
    access = import_module("app.services.organization_access")
    monkeypatch.setitem(settings.__dict__, "organization_group_admins", {root.team_id: ["delegate"]})
    monkeypatch.setattr(upstream, "team_info", AsyncMock(side_effect=HTTPException(403, "Native team-admin license unavailable")))
    scope = await access.resolve_scope(actor)
    assert scope.roots == (root.id,)
    upstream.team_info.assert_not_awaited()
    monkeypatch.setitem(settings.__dict__, "organization_access_designations", {})
    with pytest.raises(HTTPException) as denied:
        await access.resolve_scope(actor)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_designation_requires_live_admin_and_revocation_applies_after_cache_ttl(monkeypatch, scoped):
    _, root, actor = scoped
    assert util.find_spec("app.services.organization_access") is not None, "Organization capability resolver is required"
    access = import_module("app.services.organization_access")
    clock = [1000.0]
    monkeypatch.setattr(access, "monotonic", lambda: clock[0])
    scope = await access.resolve_scope(actor)
    assert scope.roots == (root.id,)
    assert not scope.global_admin
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"members_with_roles": []}}))
    # Repeated organization requests within the TTL reuse one native lookup.
    assert (await access.resolve_scope(actor)).roots == (root.id,)
    upstream.team_info.assert_not_awaited()
    clock[0] += access.ADMIN_TTL
    with pytest.raises(HTTPException) as denied:
        await access.resolve_scope(actor)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_keys_cannot_claim_global_or_delegated_capabilities(scoped):
    _, _, actor = scoped
    access = import_module("app.services.organization_access")
    actor.user.role = "admin"
    actor.proof_key = "proof"
    with pytest.raises(HTTPException) as denied:
        await access.resolve_scope(actor)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_reports_hide_parent_paths_issues_and_never_fetch_other_teams(monkeypatch, scoped):
    tree, root, actor = scoped
    access = import_module("app.services.organization_access")
    scope = await access.resolve_scope(actor)
    upstream.team_info.reset_mock()
    result = await reports.overview(scope)
    assert {group["id"] for group in result["groups"]} == {node.id for node in tree.nodes.values() if node.path[:2] == root.path}
    root_row = next(group for group in result["groups"] if group["id"] == root.id)
    assert root_row["path"] == ["Digital"]
    assert root_row["parent_id"] is None
    assert result["levels"] == ["Business Unit", "Squad"]
    assert root_row["level"] == 0
    assert result["issues"] == []
    assert result["total_users"] == 1
    assert all(
        scope.allows(next(node for node in tree.nodes.values() if node.team_id == call.args[0])) for call in upstream.team_info.await_args_list
    )
    children = await reports.children(None, scope)
    assert [group["id"] for group in children["groups"]] == [root.id]
    users = await reports.users(None, 1, 25, scope)
    assert users["total"] == 1
    assert users["users"][0]["path"] == ["Digital", "squad1"]
    with pytest.raises(HTTPException) as hidden:
        await reports.group_detail(tree.roots[0].id, scope)
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", ["undesignated", "user", "unavailable", "wrong_team"])
async def test_unknown_or_insufficient_authority_fails_closed(monkeypatch, scoped, authority):
    _, root, actor = scoped
    access = import_module("app.services.organization_access")
    if authority == "undesignated":
        monkeypatch.setattr(settings, "organization_access_designations", {})
    elif authority == "user":
        monkeypatch.setattr(
            upstream, "team_info", AsyncMock(return_value={"team_info": {"members_with_roles": [{"user_id": "delegate", "role": "user"}]}})
        )
    elif authority == "wrong_team":
        monkeypatch.setattr(
            upstream,
            "team_info",
            AsyncMock(return_value={"team_info": {"team_id": "another", "members_with_roles": [{"user_id": "delegate", "role": "admin"}]}}),
        )
    else:
        monkeypatch.setattr(upstream, "team_info", AsyncMock(side_effect=HTTPException(502, "unavailable")))
    with pytest.raises(HTTPException) as denied:
        await access.resolve_scope(actor)
    assert denied.value.status_code == 403
    assert await access.capabilities(actor) == {"organization": False, "global_admin": False, "roots": []}


@pytest.mark.asyncio
async def test_transient_upstream_failure_serves_last_good_answer_only_briefly(monkeypatch, scoped):
    _, root, actor = scoped
    access = import_module("app.services.organization_access")
    clock = [1000.0]
    monkeypatch.setattr(access, "monotonic", lambda: clock[0])
    assert (await access.resolve_scope(actor)).roots == (root.id,)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(side_effect=HTTPException(502, "unavailable")))
    clock[0] += access.ADMIN_TTL
    assert (await access.resolve_scope(actor)).roots == (root.id,)
    upstream.team_info.assert_awaited_once()
    clock[0] += access.STALE_TTL
    with pytest.raises(HTTPException) as denied:
        await access.resolve_scope(actor)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_multiple_designated_roots_include_descendants_without_descendant_admin(monkeypatch, scoped):
    tree, root, actor = scoped
    other = next(node for node in tree.nodes.values() if node.member.name == "Campaigns")
    monkeypatch.setattr(settings, "organization_access_designations", {"delegate": [root.team_id, other.team_id]})
    access = import_module("app.services.organization_access")
    scope = await access.resolve_scope(actor)
    assert scope.roots == (root.id, other.id)
    assert scope.allows(tree.resolve("alice", ["squad1"]))
    assert not scope.allows(tree.roots[0])


@pytest.mark.asyncio
async def test_http_scope_and_navigation_capability(scoped):
    import httpx
    from app.main import app
    from app.routers.api_actor import get_api_actor

    tree, root, actor = scoped
    app.dependency_overrides[get_api_actor] = lambda: actor
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as browser:
            access = await browser.get("/api/v1/organization/access")
            assert access.json() == {"organization": True, "global_admin": False, "roots": [root.id]}
            assert (await browser.get("/api/v1/organization")).status_code == 200
            hidden = tree.roots[0].id
            for path in (f"/groups/{hidden}", f"/children?parent={hidden}", f"/users?node={hidden}", f"/usage?node={hidden}"):
                assert (await browser.get("/api/v1/organization" + path)).status_code == 404
            actor.proof_key = "proof"
            assert (await browser.get("/api/v1/organization/access")).json()["organization"] is False
    finally:
        app.dependency_overrides.pop(get_api_actor, None)


@pytest.mark.asyncio
async def test_omitted_usage_scope_groups_by_authorized_roots(monkeypatch, scoped):
    _, root, actor = scoped
    access = import_module("app.services.organization_access")
    scope = await access.resolve_scope(actor)
    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(return_value=[]))
    reports._usage_cache.clear()
    today = datetime.now(timezone.utc).date()
    result = await reports.usage(None, today, today, scope)
    assert result["users"] == 1
    assert [group["id"] for group in result["by_group"]] == [root.id]
    assert result["issues"] == []
