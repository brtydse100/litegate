"""Ownership is evidence of creation, and cleanup never races a remote addition."""

from importlib import import_module, util
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, local_users, organization_client as upstream
from app.services import organization_retirement  # Bind settings before configuration reload tests.
from tests.test_organization_config import example


@pytest.fixture
def retirement(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "retirement.db"))
    local_users.init_db()
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(example()))
    monkeypatch.setattr(settings, "organization_cleanup_enabled", True)
    monkeypatch.setattr(organization_retirement, "_reported", {})
    monkeypatch.setattr(litellm, "delete_team", AsyncMock())
    monkeypatch.setattr(
        upstream,
        "team_info",
        AsyncMock(return_value={"team_info": {"team_id": "removed", "members_with_roles": []}, "team_memberships": [], "keys": [], "total_keys": 0}),
    )


@pytest.mark.asyncio
async def test_unowned_adopted_team_never_becomes_cleanup_candidate(monkeypatch, retirement):
    assert util.find_spec("app.services.organization_retirement") is not None, "Owned team retirement service is required"
    service = import_module("app.services.organization_retirement")
    monkeypatch.setattr(litellm, "get_team", AsyncMock(return_value={"team_id": "engineering"}))
    await upstream.sync_root(settings.organization_hierarchy.roots[0])
    assert service.owned_teams() == []
    assert await service.assess_removed_teams() == []
    litellm.delete_team.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_confirmed_creation_is_marked_owned(monkeypatch, retirement):
    service = import_module("app.services.organization_retirement")
    monkeypatch.setattr(litellm, "get_team", AsyncMock(return_value=None))

    async def create(payload):
        return payload

    monkeypatch.setattr(litellm, "create_team", create)
    await upstream.sync_root(settings.organization_hierarchy.roots[0])
    assert service.owned_teams() == ["engineering"]


@pytest.mark.asyncio
async def test_empty_owned_removed_team_requires_atomic_upstream_delete(monkeypatch, retirement):
    service = import_module("app.services.organization_retirement")
    service.mark_created("removed")
    result = await service.assess_removed_teams()
    assert result == [{"team_id": "removed", "status": "review_required", "reason": "atomic_delete_unavailable"}]
    litellm.delete_team.assert_not_awaited()
    with local_users.connect() as db:
        assert db.execute("SELECT count(*) FROM audit_events WHERE action='organization.retirement'").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_group_admin_team_reference_is_not_a_retirement_candidate(monkeypatch, retirement):
    service = import_module("app.services.organization_retirement")
    service.mark_created("removed")
    monkeypatch.setattr(settings, "organization_group_admins", {"removed": ["group-admin-user"]})

    assert "group-admin-user" not in service.configured_team_ids()
    assert await service.retirement_reason("removed") == "configured_reference"
    assert await service.assess_removed_teams() == []
    upstream.team_info.assert_not_awaited()
    litellm.delete_team.assert_not_awaited()
    with local_users.connect() as db:
        assert db.execute("SELECT count(*) FROM audit_events WHERE action='organization.retirement'").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_repeated_passes_audit_a_candidate_only_when_its_reason_changes(monkeypatch, retirement):
    service = import_module("app.services.organization_retirement")
    service.mark_created("removed")

    def events():
        with local_users.connect() as db:
            return [row[0] for row in db.execute("SELECT details_json FROM audit_events WHERE action='organization.retirement' ORDER BY id")]

    for _ in range(3):
        assert (await service.assess_removed_teams())[0]["reason"] == "atomic_delete_unavailable"
    assert len(events()) == 1
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"members_with_roles": [{"user_id": "late"}]}}))
    await service.assess_removed_teams()
    await service.assess_removed_teams()
    assert len(events()) == 2
    assert "remote_check_incomplete" in events()[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remote",
    [{}, {"team_info": {"members_with_roles": [{"user_id": "concurrent"}]}}, {"team_info": {"members_with_roles": []}, "keys": [{"token": "hash"}]}],
)
async def test_unknown_or_populated_remote_never_deletes(monkeypatch, retirement, remote):
    service = import_module("app.services.organization_retirement")
    service.mark_created("removed")
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=remote))
    result = await service.assess_removed_teams()
    assert result[0]["status"] == "review_required"
    litellm.delete_team.assert_not_awaited()


@pytest.mark.asyncio
async def test_retirement_pass_starts_even_when_last_hierarchy_group_was_removed(monkeypatch):
    from app.main import app, lifespan
    from app.services import organization_sync

    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    monkeypatch.setattr(settings, "organization_cleanup_enabled", True)
    monkeypatch.setattr(settings, "analytics_enabled", False)
    monkeypatch.setattr(litellm, "start_client", AsyncMock())
    monkeypatch.setattr(litellm, "close_client", AsyncMock())
    first = AsyncMock()
    monkeypatch.setattr(organization_sync, "reconciliation_attempt", first)
    monkeypatch.setattr(organization_sync, "run_reconciliation", AsyncMock())
    async with lifespan(app):
        first.assert_awaited_once()
