"""TEAM_BUDGET_WINDOWS: one shared schedule, a per-team amount per window."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.budget_windows import BudgetWindows
from app.config import Settings, settings
from app.main import app
from app.organization import OrganizationHierarchy
from app.rate_limit import _key_ops
from app.routers import auth
from app.services import litellm, local_users, organization_client as upstream, team_budget_window_sync, team_budget_windows as windows

MORNING = "sched:Europe/Berlin:mon,tue,wed,thu,fri:08:00-13:00"
AFTERNOON = "sched:Europe/Berlin:mon,tue,wed,thu,fri:13:00-18:00"
SCHEDULE = {
    "timezone": "Europe/Berlin",
    "windows": [
        {"id": "morning", "days": ["mon", "tue", "wed", "thu", "fri"], "start": "08:00", "end": "13:00"},
        {"id": "afternoon", "days": ["fri", "thu", "wed", "tue", "mon"], "start": "13:00", "end": "18:00"},
    ],
}


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "team_budget_windows", BudgetWindows.model_validate(SCHEDULE))
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "windows.db"))
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "admin_groups", "")
    monkeypatch.setattr(settings, "inherit_litellm_admin", False)
    _key_ops.clear()
    local_users.init_db()


def admin():
    return {"Authorization": "Bearer " + auth._make_jwt("a", "a@example.com", "admin")}


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def team(*limits):
    return {"team_info": {"team_id": "t1", "budget_limits": list(limits)}}


def configured(value):
    return Settings(litellm_master_key="sk-test", jwt_secret="x" * 32, team_budget_windows=value)


def test_labels_match_litellm_and_blank_disables():
    config = configured(SCHEDULE).team_budget_windows
    assert [window["label"] for window in config.public()["windows"]] == [MORNING, AFTERNOON]
    assert configured("").team_budget_windows is None


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": "Mars/Base"},
        {"windows": [{"id": "a", "start": "08:00", "end": "13:00"}, {"id": "b", "start": "12:00", "end": "14:00"}]},
        {"windows": [{"id": "a", "days": [], "start": "08:00", "end": "09:00"}]},
        {"windows": [{"id": "a", "start": "8:00", "end": "09:00"}]},
        {"windows": [{"id": "a", "start": "08:00", "end": "09:00"}, {"id": "a", "start": "10:00", "end": "11:00"}]},
        {"windows": [{"id": "Morning Shift", "start": "08:00", "end": "09:00"}]},
        {"windows": [{"start": "08:00", "end": "09:00"}]},
        {"teams": {"product": {"evening": 5}}},
        {"teams": {"product": {"morning": -1}}},
        {"teams": {"": {"morning": 1}}},
        {
            "windows": [
                {"id": "a", "days": ["sun"], "start": "22:00", "end": "06:00"},
                {"id": "b", "days": ["mon"], "start": "05:00", "end": "07:00"},
            ]
        },
    ],
)
def test_invalid_schedules_fail_at_startup(change):
    with pytest.raises(ValidationError):
        configured({**SCHEDULE, **change})


def test_merge_keeps_plain_limits_and_omits_unlimited_windows():
    current = {"budget_limits": [{"budget_duration": "7d", "max_budget": 50, "reset_at": None}, {"budget_duration": MORNING, "max_budget": 5}]}
    assert windows.amounts(current) == {"morning": 5, "afternoon": None}
    assert windows.merge(current, {"morning": 5, "afternoon": 3}) == [
        {"budget_duration": "7d", "max_budget": 50},
        {"max_budget": 5, "schedule": {"timezone": "Europe/Berlin", "days": ["mon", "tue", "wed", "thu", "fri"], "start": "08:00", "end": "13:00"}},
        {"max_budget": 3, "schedule": {"timezone": "Europe/Berlin", "days": ["mon", "tue", "wed", "thu", "fri"], "start": "13:00", "end": "18:00"}},
    ]
    assert windows.merge(current, {"morning": None}) == [{"budget_duration": "7d", "max_budget": 50}]
    with pytest.raises(HTTPException) as error:
        windows.choose(current, {"Evening": 1})
    assert error.value.status_code == 422


def with_defaults(monkeypatch, morning, afternoon, teams=None):
    schedule = {
        **SCHEDULE,
        "windows": [{**SCHEDULE["windows"][0], "budget": morning}, {**SCHEDULE["windows"][1], "budget": afternoon}],
        "teams": teams or {},
    }
    monkeypatch.setattr(settings, "team_budget_windows", BudgetWindows.model_validate(schedule))


@pytest.mark.asyncio
async def test_configured_team_caps_win_and_are_locked(monkeypatch):
    with_defaults(monkeypatch, 40, 10, {"t1": {"morning": 15}, "research": {"morning": None}})
    custom = {"team_id": "t1", "metadata": {windows.OVERRIDES: {"morning": 2, "afternoon": 3}}}
    assert windows.caps(windows.overrides(custom), "t1") == {"morning": 15, "afternoon": 3}
    assert windows.caps({}, "research") == {"morning": None, "afternoon": 10}
    assert windows.decorate(custom) == {"window_budgets": {"afternoon": 3}, "window_config": {"morning": 15}}
    with pytest.raises(HTTPException) as locked:
        windows.choose(custom, {"morning": 5})
    assert locked.value.status_code == 409
    assert windows.choose(custom, {"morning": "config"}) == {"afternoon": 3}
    # Configuration also applies to a team created with a configured ID, and is hidden publicly.
    created = await windows.apply(None, {"team_id": "research"}, None)
    assert [entry["max_budget"] for entry in created["budget_limits"]] == [10]
    assert "teams" not in settings.team_budget_windows.public()


def test_teams_follow_defaults_unless_they_override(monkeypatch):
    with_defaults(monkeypatch, 40, 10)
    marked = {"metadata": {"owner": "ops", windows.OVERRIDES: {"afternoon": None, "gone": 3}}}
    assert windows.overrides(marked) == {"afternoon": None}
    assert windows.caps(windows.overrides(marked)) == {"morning": 40, "afternoon": None}
    # Teams capped before defaults existed keep their caps as overrides; blanks follow the default.
    legacy = {"budget_limits": [{"budget_duration": AFTERNOON, "max_budget": 7}]}
    assert windows.caps(windows.overrides(legacy)) == {"morning": 40, "afternoon": 7}
    chosen = windows.choose(marked, {"morning": 2, "afternoon": "config"})
    assert chosen == {"morning": 2}
    update = windows.synced(marked, chosen)
    assert [entry["max_budget"] for entry in update["budget_limits"]] == [2, 10]
    assert update["metadata"] == {"owner": "ops", windows.OVERRIDES: {"morning": 2}}


@pytest.mark.asyncio
async def test_create_and_update_write_scheduled_entries(monkeypatch):
    with_defaults(monkeypatch, None, 6)
    create = AsyncMock(return_value={"team_id": "t1"})
    update = AsyncMock(return_value={"team_id": "t1"})
    monkeypatch.setattr(litellm, "create_team", create)
    monkeypatch.setattr(litellm, "update_team", update)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=team({"budget_duration": MORNING, "max_budget": 5})))
    async with client() as browser:
        created = await browser.post("/api/v1/teams", json={"team_alias": "T", "window_budgets": {"morning": 2}}, headers=admin())
        bare = await browser.post("/api/v1/teams", json={"team_alias": "U"}, headers=admin())
        updated = await browser.patch("/api/v1/teams/t1", json={"window_budgets": {"afternoon": 7}}, headers=admin())
        unlimited = await browser.patch("/api/v1/teams/t1", json={"window_budgets": {"morning": None}}, headers=admin())
        plain = await browser.patch("/api/v1/teams/t1", json={"max_budget": 9}, headers=admin())
    assert {created.status_code, bare.status_code} == {201} and {updated.status_code, unlimited.status_code, plain.status_code} == {200}
    assert [entry["max_budget"] for entry in create.await_args_list[0].args[0]["budget_limits"]] == [2, 6]
    assert [entry["max_budget"] for entry in create.await_args_list[1].args[0]["budget_limits"]] == [6]
    assert create.await_args_list[1].args[0]["metadata"] == {windows.OVERRIDES: {}}
    assert [entry["max_budget"] for entry in update.await_args_list[0].args[1]["budget_limits"]] == [5, 7]
    assert [entry["max_budget"] for entry in update.await_args_list[1].args[1]["budget_limits"]] == [6]
    assert "budget_limits" not in update.await_args_list[2].args[1]


def test_utc_offsets_become_fixed_iana_zones():
    config = configured({**SCHEDULE, "timezone": "UTC+2"}).team_budget_windows
    assert config.public()["timezone"] == "UTC+2" and config.public()["zone"] == "Etc/GMT-2"
    assert config.label(config.windows[0]) == "sched:Etc/GMT-2:mon,tue,wed,thu,fri:08:00-13:00"
    assert config.schedule(config.windows[0])["timezone"] == "Etc/GMT-2"
    assert configured({**SCHEDULE, "timezone": "UTC-5"}).team_budget_windows.zone == "Etc/GMT+5"
    assert configured({**SCHEDULE, "timezone": "UTC+0"}).team_budget_windows.zone == "UTC"
    for invalid in ("UTC+15", "UTC-13", "UTC+5:30"):
        with pytest.raises(ValidationError):
            configured({**SCHEDULE, "timezone": invalid})


@pytest.mark.asyncio
async def test_raw_budget_limits_and_unconfigured_windows_are_rejected(monkeypatch):
    monkeypatch.setattr(litellm, "create_team", AsyncMock())
    with pytest.raises(HTTPException) as raw:
        await windows.apply(None, {"budget_limits": []}, None)
    assert raw.value.status_code == 422
    monkeypatch.setattr(settings, "team_budget_windows", None)
    with pytest.raises(HTTPException) as off:
        await windows.apply(None, {}, {"morning": 1})
    assert off.value.status_code == 422
    assert await windows.apply(None, {"budget_limits": []}, None) == {"budget_limits": []}


@pytest.mark.asyncio
async def test_litellm_without_scheduled_windows_is_named():
    async def rejected():
        raise HTTPException(502, "LiteLLM team operation returned 422: extra fields not permitted")

    changes = {"budget_limits": [{"max_budget": 1, "schedule": {}}]}
    with pytest.raises(HTTPException) as error:
        await windows.guarded(rejected(), changes)
    assert "BerriAI/litellm#54147" in error.value.detail
    with pytest.raises(HTTPException) as other:
        await windows.guarded(rejected(), {"max_budget": 1})
    assert "54147" not in other.value.detail


@pytest.mark.asyncio
async def test_managed_teams_get_window_caps_but_not_plain_budget_edits(monkeypatch):
    from tests.test_organization_config import example

    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(example()))
    update = AsyncMock(return_value={"team_id": "engineering"})
    monkeypatch.setattr(litellm, "update_team", update)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=team()))
    async with client() as browser:
        caps = await browser.patch("/api/v1/teams/engineering", json={"window_budgets": {"morning": 4}}, headers=admin())
        plain = await browser.patch("/api/v1/teams/engineering", json={"max_budget": 4}, headers=admin())
    assert caps.status_code == 200
    assert plain.status_code == 409
    assert update.await_count == 1


@pytest.mark.asyncio
async def test_usage_reports_each_window(monkeypatch):
    info = team({"budget_duration": MORNING, "max_budget": 5})
    info["team_info"]["budget_limits_usage"] = {MORNING: {"current_spend": 1.5, "active": True, "next_start": "2026-11-26T07:00:00+00:00"}}
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=info))
    async with client() as browser:
        response = await browser.get("/api/v1/teams/t1/budget-windows", headers=admin())
        denied = await browser.get("/api/v1/teams/t1/budget-windows", headers={"Authorization": "Bearer " + auth._make_jwt("u", "u@example.com")})
    assert denied.status_code == 403
    morning, afternoon = response.json()["windows"]
    assert (morning["max_budget"], morning["current_spend"], morning["active"]) == (5, 1.5, True)
    assert (afternoon["max_budget"], afternoon["current_spend"]) == (None, None)
    assert (morning["source"], afternoon["source"]) == ("custom", "config")


@pytest.mark.asyncio
async def test_startup_syncs_defaults_and_drops_removed_windows(monkeypatch, caplog):
    with_defaults(monkeypatch, None, 6, {"plain": {"morning": 4}, "ghost": {"afternoon": 1}})
    teams = [
        {
            "team_id": "current",
            "budget_limits": [{"budget_duration": MORNING, "max_budget": 5}, {"budget_duration": AFTERNOON, "max_budget": 6}],
            "metadata": {windows.OVERRIDES: {"morning": 5}},
        },
        {
            "team_id": "old",
            "budget_limits": [{"budget_duration": "7d", "max_budget": 9}, {"budget_duration": "sched:UTC:mon:01:00-02:00", "max_budget": 1}],
            "metadata": {"owner": "ops", windows.OVERRIDES: {}},
        },
        {"team_id": "plain"},
    ]
    monkeypatch.setattr(litellm, "list_teams", AsyncMock(return_value={"teams": teams, "total_pages": 1}))
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_team", update)
    assert await team_budget_window_sync.sync_team_windows() == 2
    old, plain = (call.args for call in update.await_args_list)
    assert old[0] == "old" and [entry.get("budget_duration") or entry["max_budget"] for entry in old[1]["budget_limits"]] == ["7d", 6]
    assert old[1]["metadata"] == {"owner": "ops", windows.OVERRIDES: {}}
    assert plain[0] == "plain" and [entry["max_budget"] for entry in plain[1]["budget_limits"]] == [4, 6]
    assert "teams not found in LiteLLM: ghost" in caplog.text
    with local_users.connect() as db:
        rows = db.execute("SELECT target, outcome FROM audit_events WHERE action='team.budget_windows_synced'").fetchall()
    assert sorted(tuple(row) for row in rows) == [("old", "success"), ("plain", "success")]


@pytest.mark.asyncio
async def test_portal_config_exposes_the_schedule(monkeypatch):
    async with client() as browser:
        enabled = (await browser.get("/api/portal-config")).json()["team_budget_windows"]
        monkeypatch.setattr(settings, "team_budget_windows", None)
        disabled = (await browser.get("/api/portal-config")).json()["team_budget_windows"]
    assert [window["id"] for window in enabled["windows"]] == ["morning", "afternoon"]
    assert disabled is None


@pytest.mark.asyncio
async def test_default_caps_are_admin_only(monkeypatch):
    with_defaults(monkeypatch, 40, None)
    user = {"Authorization": "Bearer " + auth._make_jwt("u", "u@example.com")}
    async with client() as browser:
        public = (await browser.get("/api/portal-config")).json()["team_budget_windows"]
        schedule = await browser.get("/api/v1/budget-windows", headers=admin())
        denied = await browser.get("/api/v1/budget-windows", headers=user)
    assert all("budget" not in window for window in public["windows"])
    assert [window["budget"] for window in schedule.json()["windows"]] == [40, None]
    assert "key_budget_duration" not in schedule.json() and denied.status_code == 403


def test_weekend_and_single_day_windows_and_team_overrides_by_id():
    config = configured(
        {
            "timezone": "UTC",
            "windows": [
                {"id": "weekend", "days": ["sat", "sun"], "start": "00:00", "end": "00:00", "budget": 10},
                {"id": "nights", "days": ["mon", "tue", "wed", "thu"], "start": "22:00", "end": "06:00"},
                {"id": "friday", "days": ["fri"], "start": "09:00", "end": "17:00", "budget": 5},
            ],
            "teams": {"product": {"friday": 20}, "research": {"weekend": None}},
        }
    ).team_budget_windows
    assert [window.id for window in config.windows] == ["weekend", "nights", "friday"]
    assert config.teams == {"product": {"friday": 20}, "research": {"weekend": None}}


@pytest.mark.asyncio
async def test_advanced_updates_keep_the_new_window_choices(monkeypatch):
    from app.services import policy_team_update

    with_defaults(monkeypatch, 40, 10)
    current = {"team_id": "t1", "metadata": {"owner": "ops", windows.OVERRIDES: {"morning": 5}}}
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": current}))
    update = AsyncMock(return_value={"team_id": "t1"})
    monkeypatch.setattr(litellm, "update_team", update)
    changes = await windows.apply("t1", {"team_alias": "T"}, {"morning": None})
    await policy_team_update.update("t1", changes)
    sent = update.await_args.args[1]
    # Other metadata is still the server's copy; the window choice is the new one.
    assert sent["metadata"] == {"owner": "ops", windows.OVERRIDES: {"morning": None}}
    assert [entry["max_budget"] for entry in sent["budget_limits"]] == [10]
