"""Reporting totals come from complete daily aggregates and preserve role scoping."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import organization_client as upstream, organization_reports as reports, organization_store as store
from tests.test_organization_config import example


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "organization.db"))
    reports._usage_cache.clear()
    store.remember("alice", "alice@example.com", "sso", ["squad1"])
    store.remember("bob", "bob@example.com", "sso", ["squad2"])
    return tree


def row(day, spend, tokens=100, requests=2):
    return {
        "date": day.isoformat(),
        "metrics": {"spend": spend, "total_tokens": tokens, "api_requests": requests},
        "breakdown": {"models": {"model-a": {"spend": spend, "total_tokens": tokens, "api_requests": requests}}},
    }


@pytest.mark.asyncio
async def test_usage_aggregates_users_by_current_path_and_includes_zero_days(monkeypatch, setup):
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    fetch = AsyncMock(side_effect=[[row(day, 10)], [row(day, 5)]])
    monkeypatch.setattr(upstream, "daily_usage", fetch)
    node = next(node for node in setup.nodes.values() if node.member.name == "Digital")
    result = await reports.usage(node.id, day - timedelta(days=1), day)
    assert result["totals"] == {"spend": 15, "tokens": 200, "requests": 4}
    assert result["daily"][0]["spend"] == 0
    assert {value["name"]: value["spend"] for value in result["by_group"]} == {"squad1": 10, "squad2": 5}
    assert result["by_model"][0]["spend"] == 15
    assert result["attribution"] == "current_membership"
    await reports.usage(node.id, day - timedelta(days=1), day)
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_leaf_selection_queries_only_members_in_that_group(monkeypatch, setup):
    day = datetime.now(timezone.utc).date()
    fetch = AsyncMock(return_value=[row(day, 10)])
    monkeypatch.setattr(upstream, "daily_usage", fetch)
    node = setup.resolve("alice", ["squad1"])
    result = await reports.usage(node.id, day, day)
    assert result["users"] == 1
    fetch.assert_awaited_once_with("alice", day.isoformat(), day.isoformat())
    assert result["by_group"] == [{"name": "Direct members", "spend": 10, "tokens": 100, "requests": 2}]


@pytest.mark.asyncio
async def test_a_failed_upstream_report_never_returns_partial_totals(monkeypatch):
    monkeypatch.setattr(upstream, "daily_usage", AsyncMock(side_effect=HTTPException(status_code=502, detail="Aggregate unavailable")))
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
    monkeypatch.setattr(upstream, "daily_usage", AsyncMock(return_value=[row(day + timedelta(days=1), 5)]))
    with pytest.raises(HTTPException):
        await reports.usage(None, day, day)
    reports._usage_cache.clear()
    monkeypatch.setattr(upstream, "daily_usage", AsyncMock(return_value=[row(day, float("nan"))]))
    with pytest.raises(HTTPException):
        await reports.usage(None, day, day)


@pytest.mark.asyncio
async def test_range_and_group_validation_happens_before_reading_usage(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(upstream, "daily_usage", fetch)
    with pytest.raises(HTTPException):
        await reports.usage("missing", datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date())
    with pytest.raises(HTTPException):
        await reports.usage(None, datetime.now(timezone.utc).date() - timedelta(days=100), datetime.now(timezone.utc).date())
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_pagination_and_cycle_spend_are_independent_of_report_totals(monkeypatch, setup):
    info = {"team_memberships": [{"user_id": "alice", "spend": 42}, {"user_id": "bob", "spend": 20}]}
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=info))
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
    value = row(day, 10)
    metrics = value["breakdown"]["models"]["model-a"]
    value["breakdown"]["models"]["model-a"] = {"metrics": metrics, "metadata": {"api_key": "redacted"}}
    monkeypatch.setattr(upstream, "daily_usage", AsyncMock(return_value=[value]))
    result = await reports.usage(None, day, day)
    assert result["by_model"] == [{"name": "model-a", "spend": 20, "tokens": 200, "requests": 4}]


@pytest.mark.asyncio
async def test_ignored_root_budget_writes_are_visible_even_when_team_is_readable(monkeypatch):
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"max_budget": 10, "budget_duration": "30d", "spend": 4}}))
    result = await reports.overview()
    assert result["groups"][0]["group_spend"] == 4
    assert "differs" in result["groups"][0]["sync_error"]


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
