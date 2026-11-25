"""TEAM_BUDGET_DURATION gives every team the same LiteLLM-aligned reset window."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings, settings
from app.main import app
from app.organization import OrganizationHierarchy
from app.rate_limit import _key_ops
from app.routers import auth
from app.services import litellm, local_users, team_budget_window
from tests.test_organization_config import example


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "team_budget_duration", "1mo")
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "window.db"))
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "admin_groups", "")
    monkeypatch.setattr(settings, "inherit_litellm_admin", False)
    _key_ops.clear()
    local_users.init_db()


def admin():
    return {"Authorization": "Bearer " + auth._make_jwt("a", "a@example.com", "admin")}


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def audit_outcomes() -> list[str]:
    with local_users.connect() as db:
        return [row[0] for row in db.execute("SELECT outcome FROM audit_events WHERE action='team.budget_window_aligned' ORDER BY target")]


def test_blank_setting_disables_the_window():
    configured = Settings(litellm_master_key="sk-test", jwt_secret="x" * 32, team_budget_duration="")
    assert configured.team_budget_duration is None


def test_only_calendar_aligned_windows_are_accepted():
    with pytest.raises(ValidationError):
        Settings(litellm_master_key="sk-test", jwt_secret="x" * 32, team_budget_duration="30d")


def test_organization_groups_must_share_the_window():
    hierarchy = example()
    with pytest.raises(ValidationError, match="mismatched"):
        Settings(litellm_master_key="sk-test", jwt_secret="x" * 32, team_budget_duration="1mo", organization_hierarchy=hierarchy)
    for level in hierarchy["levels"]:
        for group in level["groups"]:
            for member in group["members"]:
                member.setdefault("budget", {})["duration"] = "1mo"
    configured = Settings(litellm_master_key="sk-test", jwt_secret="x" * 32, team_budget_duration="1mo", organization_hierarchy=hierarchy)
    assert configured.team_budget_duration == "1mo"


def test_apply_sets_create_rejects_others_and_never_resends_on_update(monkeypatch):
    assert team_budget_window.apply({"max_budget": 5}, create=True) == {"max_budget": 5, "budget_duration": "1mo"}
    assert team_budget_window.apply({"max_budget": None, "budget_duration": "1mo"}, create=False) == {"max_budget": None}
    for changes in ({"budget_duration": "7d"}, {"budget_duration": None}):
        with pytest.raises(HTTPException) as error:
            team_budget_window.apply(changes, create=False)
        assert error.value.status_code == 422
    monkeypatch.setattr(settings, "team_budget_duration", None)
    assert team_budget_window.apply({"budget_duration": "7d"}, create=True) == {"budget_duration": "7d"}


@pytest.mark.asyncio
async def test_created_team_gets_the_window_and_unlimited_stays_unlimited(monkeypatch):
    create = AsyncMock(return_value={"team_id": "t1"})
    monkeypatch.setattr(litellm, "create_team", create)
    async with client() as browser:
        response = await browser.post("/api/v1/teams", json={"team_alias": "Team"}, headers=admin())
        rejected = await browser.post("/api/v1/teams", json={"team_alias": "Team", "budget_duration": "7d"}, headers=admin())
    assert response.status_code == 201
    assert create.await_args.args[0]["budget_duration"] == "1mo"
    assert "max_budget" not in create.await_args.args[0]
    assert rejected.status_code == 422
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_startup_aligns_other_teams_and_reports_failures(monkeypatch):
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(example()))
    teams = [
        {"team_id": "aligned", "budget_duration": "1mo"},
        {"team_id": "drifting", "budget_duration": "30d"},
        {"team_id": "never", "budget_duration": None},
        {"team_id": "engineering", "budget_duration": "30d"},
    ]
    monkeypatch.setattr(litellm, "list_teams", AsyncMock(return_value={"teams": teams, "total_pages": 1}))

    async def update(team_id, changes):
        if team_id == "never":
            raise HTTPException(502, "down")
        return {}

    update_team = AsyncMock(side_effect=update)
    monkeypatch.setattr(litellm, "update_team", update_team)
    assert await team_budget_window.align_existing_teams() == 1
    assert sorted(call.args[0] for call in update_team.await_args_list) == ["drifting", "never"]
    assert all(call.args[1] == {"budget_duration": "1mo"} for call in update_team.await_args_list)
    assert audit_outcomes() == ["success", "failure"]


@pytest.mark.asyncio
async def test_startup_does_nothing_without_a_window(monkeypatch):
    monkeypatch.setattr(settings, "team_budget_duration", None)
    list_teams = AsyncMock()
    monkeypatch.setattr(litellm, "list_teams", list_teams)
    assert await team_budget_window.align_existing_teams() == 0
    list_teams.assert_not_awaited()


@pytest.mark.asyncio
async def test_portal_config_exposes_the_window():
    async with client() as browser:
        response = await browser.get("/api/portal-config")
    assert response.json()["team_budget_duration"] == "1mo"
