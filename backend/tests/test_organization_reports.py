"""Reporting totals come from complete daily aggregates and preserve role scoping."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, organization_client as upstream, organization_reports as reports, organization_store as store
from tests.test_organization_config import example


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "organization.db"))
    from app.services import database as database_service

    database_service.initialize()
    reports._usage_cache.clear()
    store.remember("alice", "alice@example.com", "sso", ["squad1"])
    store.remember("bob", "bob@example.com", "sso", ["squad2"])
    return tree


def row(day, spend, tokens=100, requests=2, owners=("alice",)):
    """One day of team activity in which each owner's key used ``spend``."""
    usage = {owner: spend for owner in owners} if not isinstance(spend, dict) else spend

    def keys():
        return {
            f"key-{owner}": {
                "metrics": {"spend": value, "total_tokens": tokens, "api_requests": requests},
                "metadata": {"user_id": owner, "team_id": "team"},
            }
            for owner, value in usage.items()
        }

    first = next(iter(usage.values()))
    totals = {"spend": first, "total_tokens": tokens, "api_requests": requests}
    return {
        "date": day.isoformat(),
        "metrics": totals,
        "breakdown": {"api_keys": keys(), "models": {"model-a": {"metrics": dict(totals), "api_key_breakdown": keys()}}},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "empty",
        "missing",
        "null",
        "nan",
        "infinity",
        "negative",
        "boolean",
        "string",
        "fractional",
        "model",
        "date",
    ],
)
async def test_invalid_aggregates_are_not_cached_and_a_corrected_retry_succeeds(monkeypatch, setup, invalid):
    day = datetime.now(timezone.utc).date()
    bad = row(day, 5)
    if invalid == "empty":
        bad["metrics"] = {}
    elif invalid == "missing":
        bad["metrics"].pop("api_requests")
    elif invalid == "model":
        bad["breakdown"]["models"]["model-a"] = {"metrics": {}}
    elif invalid == "date":
        bad["date"] = (day + timedelta(days=1)).isoformat()
    elif invalid == "fractional":
        bad["metrics"]["api_requests"] = 1.5
    else:
        bad["metrics"]["spend"] = {"null": None, "nan": float("nan"), "infinity": float("inf"), "negative": -1, "boolean": False, "string": ""}[
            invalid
        ]
    fetch = AsyncMock(side_effect=[[bad], [row(day, 5)]])
    monkeypatch.setattr(upstream, "team_daily_usage", fetch)
    node = setup.resolve("alice", ["squad1"])
    with pytest.raises(HTTPException) as exc:
        await reports.usage(node.id, day, day)
    assert exc.value.status_code == 502
    assert reports._usage_cache == {}
    result = await reports.usage(node.id, day, day)
    assert result["totals"] == {"spend": 5, "tokens": 100, "requests": 2}
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_usage_aggregates_users_by_current_path_and_includes_zero_days(monkeypatch, setup):
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    fetch = AsyncMock(return_value=[row(day, {"alice": 10, "bob": 5})])
    monkeypatch.setattr(upstream, "team_daily_usage", fetch)
    node = next(node for node in setup.nodes.values() if node.member.name == "Digital")
    result = await reports.usage(node.id, day - timedelta(days=1), day)
    assert result["totals"] == {"spend": 15, "tokens": 200, "requests": 4}
    assert result["daily"][0]["spend"] == 0
    assert {value["name"]: value["spend"] for value in result["by_group"]} == {"squad1": 10, "squad2": 5}
    assert result["by_model"][0]["spend"] == 15
    assert {value["id"]: value["spend"] for value in result["by_user"]} == {"alice": 10, "bob": 5}
    assert sum(value["tokens"] for value in result["by_user"]) == result["totals"]["tokens"]
    assert result["attribution"] == "current_membership"
    await reports.usage(node.id, day - timedelta(days=1), day)
    assert fetch.await_count == 1


@pytest.mark.asyncio
async def test_leaf_selection_counts_only_members_in_that_group(monkeypatch, setup):
    day = datetime.now(timezone.utc).date()
    fetch = AsyncMock(return_value=[row(day, {"alice": 10, "bob": 7, "not-a-member": 50})])
    monkeypatch.setattr(upstream, "team_daily_usage", fetch)
    node = setup.resolve("alice", ["squad1"])
    result = await reports.usage(node.id, day, day)
    assert result["users"] == 1
    # One request covers every managed team, whatever the selection.
    teams = sorted({item.team_id for item in setup.nodes.values()})
    fetch.assert_awaited_once_with(teams, day.isoformat(), day.isoformat())
    assert result["totals"] == {"spend": 10, "tokens": 100, "requests": 2}
    day_usage = {"date": day.isoformat(), "spend": 10, "tokens": 100, "requests": 2}
    assert result["by_group"] == [{"id": None, "name": "Direct members", "spend": 10, "tokens": 100, "requests": 2, "daily": [day_usage]}]
    assert result["by_user"] == [{"id": "alice", "name": "alice@example.com", "spend": 10, "tokens": 100, "requests": 2}]


@pytest.mark.asyncio
async def test_member_breakdown_includes_inactive_members_and_falls_back_to_user_id(monkeypatch, setup):
    store.remember("charlie", "", "sso", ["squad1"])
    day = datetime.now(timezone.utc).date()
    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(return_value=[]))
    result = await reports.usage(setup.resolve("alice", ["squad1"]).id, day, day)
    assert result["by_user"] == [
        {"id": "alice", "name": "alice@example.com", "spend": 0, "tokens": 0, "requests": 0},
        {"id": "charlie", "name": "charlie", "spend": 0, "tokens": 0, "requests": 0},
    ]


@pytest.mark.asyncio
async def test_a_failed_upstream_report_never_returns_partial_totals(monkeypatch):
    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(side_effect=HTTPException(status_code=502, detail="Aggregate unavailable")))
    with pytest.raises(HTTPException) as exc:
        await reports.usage(None, datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date())
    assert exc.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [{}, {"results": [], "metadata": {"total_pages": 2}}, {"results": [], "metadata": {"has_more": True}}])
async def test_incomplete_daily_response_is_rejected(monkeypatch, data):
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value=data))
    with pytest.raises(HTTPException):
        await upstream.daily_usage("alice", "2026-09-01", "2026-09-02")


@pytest.mark.asyncio
async def test_invalid_upstream_dates_and_nan_do_not_pollute_reports(monkeypatch):
    day = datetime.now(timezone.utc).date()
    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(return_value=[row(day + timedelta(days=1), 5)]))
    with pytest.raises(HTTPException):
        await reports.usage(None, day, day)
    assert reports._usage_cache == {}
    reports._usage_cache.clear()
    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(return_value=[row(day, float("nan"))]))
    with pytest.raises(HTTPException):
        await reports.usage(None, day, day)


@pytest.mark.asyncio
async def test_range_and_group_validation_happens_before_reading_usage(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(upstream, "team_daily_usage", fetch)
    with pytest.raises(HTTPException):
        await reports.usage("missing", datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date())
    with pytest.raises(HTTPException):
        await reports.usage(None, datetime.now(timezone.utc).date() - timedelta(days=100), datetime.now(timezone.utc).date())
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_pagination_and_cycle_spend_are_independent_of_report_totals(monkeypatch, setup):
    info = {"team_memberships": [{"user_id": "alice", "spend": 42}, {"user_id": "bob", "spend": 20}]}
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=info))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(side_effect=[[{"spend": 42}], [{"spend": 20}]]))
    first = await reports.users(None, 1, 1)
    second = await reports.users(None, 2, 1)
    assert first["total"] == 2
    assert first["users"][0]["budget_spend"] == 42
    assert first["users"][0]["per_user"] == 100
    assert second["users"][0]["user_id"] == "bob"
    assert second["users"][0]["per_user"] == 50


@pytest.mark.asyncio
async def test_root_outage_is_visible_without_inventing_zero_spend(monkeypatch):
    monkeypatch.setattr(upstream, "team_info", AsyncMock(side_effect=HTTPException(status_code=502, detail="Unavailable")))
    result = await reports.overview()
    assert result["groups"][0]["group_spend"] is None
    assert result["groups"][0]["sync_error"] == "Unavailable"
    users = await reports.users(None, 1, 25)
    assert users["users"][0]["budget_spend"] is None


@pytest.mark.asyncio
async def test_current_litellm_nested_model_metrics_are_used(monkeypatch):
    day = datetime.now(timezone.utc).date()
    value = row(day, {"alice": 10, "bob": 10, "not-a-member": 99})
    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(return_value=[value]))
    result = await reports.usage(None, day, day)
    # Model totals are counted per key owner, so non-members never appear.
    assert result["by_model"] == [{"name": "model-a", "spend": 20, "tokens": 200, "requests": 4}]


@pytest.mark.asyncio
async def test_ignored_root_budget_writes_are_visible_even_when_team_is_readable(monkeypatch):
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"max_budget": 10, "budget_duration": "30d", "spend": 4}}))
    result = await reports.overview()
    assert result["groups"][0]["group_spend"] == 4 * sum(node.path[0] == "Engineering" for node in settings.organization_hierarchy.nodes.values())
    assert "pending" in result["groups"][0]["sync_error"]


@pytest.mark.asyncio
async def test_paginated_daily_records_combine_the_same_day_and_model_without_losing_totals(monkeypatch, setup):
    day = datetime.now(timezone.utc).date()
    fetch = AsyncMock(
        side_effect=[
            {"results": [row(day, 10)], "metadata": {"page": 1, "total_pages": 2, "has_more": True}},
            {"results": [row(day, 5)], "metadata": {"page": 2, "total_pages": 2, "has_more": False}},
        ]
    )
    monkeypatch.setattr(upstream, "request", fetch)
    node = setup.resolve("alice", ["squad1"])
    result = await reports.usage(node.id, day, day)
    assert result["totals"] == {"spend": 15, "tokens": 200, "requests": 4}
    assert result["daily"][0]["spend"] == 15
    assert result["by_model"][0]["spend"] == 15
    assert [call.kwargs["params"]["page"] for call in fetch.call_args_list] == [1, 2]
    await reports.usage(node.id, day, day)
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_a_later_page_failure_never_caches_or_returns_partial_data(monkeypatch, setup):
    day = datetime.now(timezone.utc).date()
    fetch = AsyncMock(
        side_effect=[
            {"results": [row(day, 10)], "metadata": {"page": 1, "total_pages": 2, "has_more": True}},
            HTTPException(status_code=502, detail="Page two failed"),
        ]
    )
    monkeypatch.setattr(upstream, "request", fetch)
    node = setup.resolve("alice", ["squad1"])
    with pytest.raises(HTTPException, match="Page two failed"):
        await reports.usage(node.id, day, day)
    assert reports._usage_cache == {}


@pytest.mark.asyncio
async def test_pagination_is_bounded_and_ignored_page_parameters_are_rejected(monkeypatch):
    fetch = AsyncMock(return_value={"results": [], "metadata": {"total_pages": 21}})
    monkeypatch.setattr(upstream, "request", fetch)
    with pytest.raises(HTTPException) as exc:
        await upstream.daily_usage("alice", "2026-09-01", "2026-09-02")
    assert exc.value.status_code == 422
    assert fetch.await_count == 1
    fetch.side_effect = [
        {"results": [{"date": "2026-09-01"}], "metadata": {"page": 1, "total_pages": 2}},
        {"results": [{"date": "2026-09-01"}], "metadata": {"page": 1, "total_pages": 2}},
    ]
    with pytest.raises(HTTPException) as exc:
        await upstream.daily_usage("alice", "2026-09-01", "2026-09-02")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_has_more_without_a_page_count_is_supported_but_cannot_loop_forever(monkeypatch):
    fetch = AsyncMock(return_value={"results": [{"date": "2026-09-01"}], "metadata": {"has_more": True}})
    monkeypatch.setattr(upstream, "request", fetch)
    with pytest.raises(HTTPException) as exc:
        await upstream.daily_usage("alice", "2026-09-01", "2026-09-02")
    assert exc.value.status_code == 422
    assert fetch.await_count == 20
    fetch.reset_mock()
    fetch.side_effect = [
        {"results": [{"date": "2026-09-01"}], "metadata": {"has_more": True}},
        {"results": [{"date": "2026-09-01"}], "metadata": {"has_more": False}},
    ]
    assert len(await upstream.daily_usage("alice", "2026-09-01", "2026-09-02")) == 2
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_report_deadline_is_an_explicit_error_and_leaves_the_cache_empty(monkeypatch, setup):
    monkeypatch.setattr(upstream, "request", AsyncMock(side_effect=TimeoutError))
    day = datetime.now(timezone.utc).date()
    node = setup.resolve("alice", ["squad1"])
    with pytest.raises(HTTPException) as exc:
        await reports.usage(node.id, day, day)
    assert exc.value.status_code == 504
    assert reports._usage_cache == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_caller", [False, True])
async def test_failed_or_cancelled_report_cancels_and_awaits_active_and_queued_fetches(monkeypatch, cancel_caller):
    for index in range(18):
        store.remember(f"user-{index}", "", "sso", ["squad1"])
    started, cancelled = set(), set()
    ready, fail, cleanup_started, cleanup_release = (asyncio.Event() for _ in range(4))
    error = HTTPException(status_code=502, detail="Analytics failed")

    teams = sorted({node.team_id for node in settings.organization_hierarchy.nodes.values()})
    monkeypatch.setattr(reports, "USAGE_TEAM_BATCH", 1)

    async def fetch(team_ids, start, end):
        (team,) = team_ids
        started.add(team)
        if len(started) == 4:
            ready.set()
        try:
            await fail.wait()
            if team == teams[0] and not cancel_caller:
                raise error
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.add(team)
            cleanup_started.set()
            await cleanup_release.wait()
            raise

    monkeypatch.setattr(upstream, "team_daily_usage", fetch)
    day = datetime.now(timezone.utc).date()
    report = asyncio.create_task(reports.usage(None, day, day))
    try:
        await asyncio.wait_for(ready.wait(), 2)
        if cancel_caller:
            report.cancel()
        else:
            fail.set()
        await asyncio.wait_for(cleanup_started.wait(), 2)
        assert not report.done()
        cleanup_release.set()
        with pytest.raises(asyncio.CancelledError if cancel_caller else HTTPException) as exc:
            await asyncio.wait_for(report, 2)
        if not cancel_caller:
            assert exc.value is error
        assert cancelled == started - (set() if cancel_caller else {teams[0]})
        assert len(started) < len(teams)
        completed = set(started)
        await asyncio.sleep(0)
        assert started == completed
        assert reports._usage_cache == {}
    finally:
        cleanup_release.set()
        report.cancel()
        await asyncio.gather(report, return_exceptions=True)


@pytest.mark.asyncio
async def test_direct_members_and_a_child_with_that_name_have_distinct_group_ids(monkeypatch):
    values = example()
    values["levels"][2]["groups"][0]["members"][0]["name"] = "Direct members"
    tree = OrganizationHierarchy.model_validate(values)
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    store.remember("alice", "alice@example.com", "sso", ["digital"])
    store.remember("bob", "bob@example.com", "sso", ["squad1"])
    day = datetime.now(timezone.utc).date()

    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(return_value=[row(day, {"alice": 10, "bob": 5})]))
    parent = tree.resolve("alice", ["digital"])
    child = tree.resolve("bob", ["squad1"])
    result = await reports.usage(parent.id, day, day)
    assert result["totals"]["spend"] == 15
    assert {bucket["id"]: bucket["spend"] for bucket in result["by_group"]} == {None: 10, child.id: 5}
    assert [bucket["name"] for bucket in result["by_group"]] == ["Direct members", "Direct members"]
    detail = await reports.usage(child.id, day, day)
    assert detail["users"] == 1
    assert detail["totals"]["spend"] == 5


def squads(tree):
    return [next(node for node in tree.nodes.values() if node.path[-1] == name) for name in ("squad1", "squad2")]


@pytest.mark.asyncio
async def test_several_groups_combine_members_and_compare_side_by_side(monkeypatch, setup):
    squad1, squad2 = squads(setup)
    marketing = next(node for node in setup.roots if node.path == ("Marketing",))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    combined = await reports.users([squad1.id, squad2.id], 1, 25)
    assert {user["user_id"] for user in combined["users"]} == {"alice", "bob"}
    only_alice = await reports.users([squad1.id, marketing.id], 1, 25)
    assert [user["user_id"] for user in only_alice["users"]] == ["alice"]

    day = datetime.now(timezone.utc).date()
    monkeypatch.setattr(upstream, "team_daily_usage", AsyncMock(return_value=[row(day, {"alice": 3, "bob": 5})]))
    result = await reports.usage([squad1.id, squad2.id], day, day)
    # Several selected groups break down by those groups, not their children.
    assert {group["name"]: group["spend"] for group in result["by_group"]} == {"squad1": 3, "squad2": 5}
    # Each group also reports its own days, for the team-by-day grid.
    assert {group["name"]: group["daily"][0]["spend"] for group in result["by_group"]} == {"squad1": 3, "squad2": 5}
    assert result["totals"]["spend"] == 8
    assert result["users"] == 2


@pytest.mark.asyncio
async def test_selected_groups_are_validated_one_by_one(setup):
    squad1, _ = squads(setup)
    with pytest.raises(HTTPException) as missing:
        await reports.users([squad1.id, "missing"], 1, 25)
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as too_many:
        await reports.users([f"group-{index}" for index in range(reports.MAX_SELECTED_GROUPS + 1)], 1, 25)
    assert too_many.value.status_code == 422


@pytest.mark.asyncio
async def test_usage_endpoint_accepts_repeated_node_parameters(monkeypatch, setup):
    import httpx

    from app.main import app
    from app.models import CurrentUser
    from app.routers.api_actor import ApiActor, get_api_actor

    squad1, squad2 = squads(setup)
    received = AsyncMock(return_value={"users": []})
    monkeypatch.setattr(reports, "users", received)
    app.dependency_overrides[get_api_actor] = lambda: ApiActor(
        CurrentUser(user_id="root", email="root@example.invalid", role="admin", auth_source="sso")
    )
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            response = await http.get(f"/api/v1/organization/users?node={squad1.id}&node={squad2.id}")
    finally:
        app.dependency_overrides.pop(get_api_actor, None)
    assert response.status_code == 200
    assert received.await_args.args[0] == [squad1.id, squad2.id]
