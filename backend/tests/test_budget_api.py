"""Budget previews obey delegated roots and never activate on version alone."""

from importlib import import_module, util
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models import CurrentUser
from app.organization import OrganizationHierarchy
from app.routers.api_actor import ApiActor
from app.services import organization_access, organization_store


@pytest.fixture
def context(monkeypatch):
    tree = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Division",
                    "groups": [
                        {
                            "members": [
                                {"name": "Root", "litellmTeamId": "root", "budget": {"groupTotal": 100}},
                                {"name": "Other", "litellmTeamId": "other", "budget": {"groupTotal": 20}},
                            ]
                        }
                    ],
                },
                {"name": "Team", "groups": [{"parent": "Root", "members": [{"name": "Child", "userIds": ["alice", "delegate"]}]}]},
            ]
        }
    )
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "hierarchical_budgets_enabled", True)
    root = tree.roots[0]
    child = next(node for node in tree.nodes.values() if node.parent_id == root.id)
    scope = organization_access.OrganizationScope(roots=(root.id,))
    monkeypatch.setattr(organization_access, "resolve_scope", AsyncMock(return_value=scope))
    actor = ApiActor(CurrentUser(user_id="delegate", email="delegate@example.test", role="user", auth_source="sso"))
    return tree, root, child, actor


def router(monkeypatch):
    assert util.find_spec("app.routers.budgets") is not None, "Budget endpoints must be implemented"
    routes = import_module("app.routers.budgets")
    monkeypatch.setattr(routes.native, "capabilities", AsyncMock(return_value={"supported": False, "version": "1.98.0", "reasons": ["unverified"]}))
    return routes


@pytest.mark.asyncio
async def test_scope_hides_other_groups_and_root_envelope_cannot_be_edited(monkeypatch, context):
    tree, root, child, actor = context
    routes = router(monkeypatch)
    view = await routes.budget_view(actor)
    assert {row["id"] for row in view["groups"]} == {root.id, child.id}
    assert view["applied"] is False
    root_row = next(row for row in view["groups"] if row["id"] == root.id)
    assert root_row["can_edit_envelope"] is False
    with pytest.raises(HTTPException) as denied:
        await routes.edit_envelope(root.id, routes.EnvelopeEdit(revision=0, amount=200), actor)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as hidden:
        await routes.edit_envelope(tree.roots[1].id, routes.EnvelopeEdit(revision=0, amount=10), actor)
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_delegate_cannot_increase_own_allowance_indirectly(monkeypatch, context):
    _, root, child, actor = context
    routes = router(monkeypatch)
    with pytest.raises(HTTPException) as denied:
        await routes.edit_envelope(child.id, routes.EnvelopeEdit(revision=0, amount=40), actor)
    assert denied.value.status_code == 403
    assert (await routes.budget_view(actor))["revision"] == 0


@pytest.mark.asyncio
async def test_admin_edit_automatic_zero_override_and_scoped_subject_validation(monkeypatch, context):
    tree, root, child, actor = context
    routes = router(monkeypatch)
    monkeypatch.setattr(organization_access, "resolve_scope", AsyncMock(return_value=organization_access.GLOBAL_SCOPE))
    view = await routes.edit_envelope(child.id, routes.EnvelopeEdit(revision=0, amount=40), actor)
    assert view["revision"] == 1
    view = await routes.edit_override(child.id, "alice", routes.UserEdit(revision=1, amount=0), actor)
    row = next(row for row in view["groups"] if row["id"] == child.id)
    assert {u["user_id"]: u["allocation"] for u in row["users"]} == {"alice": 0, "delegate": 40}
    assert next(u for u in row["users"] if u["user_id"] == "alice")["mode"] == "manual"
    with pytest.raises(HTTPException) as absent:
        await routes.edit_override(root.id, "alice", routes.UserEdit(revision=2, amount=1), actor)
    assert absent.value.status_code == 404
    with pytest.raises(HTTPException) as stale:
        await routes.edit_override(child.id, "alice", routes.UserEdit(revision=1, amount=None), actor)
    assert stale.value.status_code == 409


@pytest.mark.asyncio
async def test_preview_never_writes_native_policy_and_activation_stays_unavailable(monkeypatch, context):
    _, _, _, actor = context
    routes = router(monkeypatch)
    monkeypatch.setattr(organization_access, "resolve_scope", AsyncMock(return_value=organization_access.GLOBAL_SCOPE))
    write = AsyncMock()
    monkeypatch.setattr(routes.native, "write_amount", write)
    with pytest.raises(HTTPException) as unavailable:
        await routes.activate(routes.Activation(revision=0), actor)
    assert unavailable.value.status_code == 503
    write.assert_not_awaited()
    assert (await routes.budget_view(actor))["mode"] == "preview"


@pytest.mark.asyncio
async def test_feature_disabled_is_not_accessible(monkeypatch, context):
    *_, actor = context
    routes = router(monkeypatch)
    monkeypatch.setattr(settings, "hierarchical_budgets_enabled", False)
    with pytest.raises(HTTPException) as hidden:
        await routes.budget_view(actor)
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_system_admin_can_repair_invalid_existing_child_envelope(monkeypatch, context):
    _, root, child, actor = context
    routes = router(monkeypatch)
    monkeypatch.setattr(organization_access, "resolve_scope", AsyncMock(return_value=organization_access.GLOBAL_SCOPE))
    from app.services import budget_store

    budget_store.edit(0, lambda state: state["envelopes"].update({root.id: 10_000_000, child.id: 20_000_000}))
    repaired = await routes.edit_envelope(child.id, routes.EnvelopeEdit(revision=1, amount=0), actor)
    assert repaired["revision"] == 2
    assert next(group for group in repaired["groups"] if group["id"] == child.id)["assigned"] == 0


@pytest.mark.asyncio
async def test_invalid_preview_remains_readable_and_only_exposes_scoped_errors(monkeypatch, context):
    tree, root, child, actor = context
    routes = router(monkeypatch)
    from app.services import budget_store

    budget_store.edit(0, lambda state: state["envelopes"].update({root.id: 10_000_000, child.id: 20_000_000}))
    view = await routes.budget_view(actor)
    assert view["revision"] == 1
    assert {row["id"] for row in view["groups"]} == {root.id, child.id}
    invalid = next(row for row in view["groups"] if row["id"] == root.id)
    assert invalid["assigned"] == 10
    assert invalid["allocated"] is None
    assert invalid["remainder"] is None
    assert invalid["allocation_error"]
    valid = next(row for row in view["groups"] if row["id"] == child.id)
    assert valid["allocation_error"] is None
    assert valid["allocated"] == 20


@pytest.mark.asyncio
async def test_admin_can_incrementally_repair_independent_invalid_groups(monkeypatch, context):
    tree, root, child, actor = context
    routes = router(monkeypatch)
    monkeypatch.setattr(organization_access, "resolve_scope", AsyncMock(return_value=organization_access.GLOBAL_SCOPE))
    from app.services import budget_store

    budget_store.edit(0, lambda state: state.update(envelopes={root.id: 10_000_000, child.id: 20_000_000}, overrides={"alice": 30_000_000}))
    first = await routes.edit_envelope(root.id, routes.EnvelopeEdit(revision=1, amount=20), actor)
    assert first["revision"] == 2
    assert next(row for row in first["groups"] if row["id"] == root.id)["allocation_error"] is None
    assert next(row for row in first["groups"] if row["id"] == child.id)["allocation_error"]
    final = await routes.edit_override(child.id, "alice", routes.UserEdit(revision=2, amount=0), actor)
    assert all(row["allocation_error"] is None for row in final["groups"])


@pytest.mark.asyncio
async def test_admin_cannot_worsen_an_invalid_group_during_repair(monkeypatch, context):
    _, root, child, actor = context
    routes = router(monkeypatch)
    monkeypatch.setattr(organization_access, "resolve_scope", AsyncMock(return_value=organization_access.GLOBAL_SCOPE))
    from app.services import budget_store

    budget_store.edit(0, lambda state: state["envelopes"].update({root.id: 10_000_000, child.id: 20_000_000}))
    with pytest.raises(HTTPException) as rejected:
        await routes.edit_envelope(child.id, routes.EnvelopeEdit(revision=1, amount=30), actor)
    assert rejected.value.status_code == 409
    assert budget_store.read()["revision"] == 1


@pytest.mark.asyncio
async def test_invalid_user_preview_preserves_manual_zero_and_marks_automatic_unknown(monkeypatch, context):
    _, _, child, actor = context
    routes = router(monkeypatch)
    from app.services import budget_store

    budget_store.edit(0, lambda state: state["overrides"].update({"alice": 30_000_000}))
    view = await routes.budget_view(actor)
    invalid = next(row for row in view["groups"] if row["id"] == child.id)
    assert invalid["allocation_error"]
    assert {user["user_id"]: user["allocation"] for user in invalid["users"]} == {"alice": 30, "delegate": None}
