"""Persistent personal analytics, with no upstream work on dashboard reads."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models import CurrentUser
from app.services import analytics, analytics_store, local_users


@pytest.fixture
def stored(tmp_path, monkeypatch):
    from app.routers import analytics as analytics_router

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 16, 12, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(analytics_router, "datetime", FixedDateTime)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "analytics.db"))
    local_users.init_db()
    with local_users.connect() as db:
        analytics_store.create_tables(db)
    analytics_store.remember_user("alice", "alice@example.invalid", "sso")
    analytics_store.remember_user("bob", "bob@example.invalid", "sso")


def rows():
    return [{"day": "2026-11-15", "model": "", "requests": 3, "tokens": 30, "input_tokens": 20, "output_tokens": 10, "cost": 0.03}]


def test_publish_is_owner_scoped_and_failed_refresh_retains_good_snapshot(stored):
    analytics_store.publish("alice", rows(), "2026-11-01", "2026-11-16", [], "2026-11-16T12:00:00+00:00")
    analytics_store.failed("alice")
    alice = analytics_store.read("alice", "2026-11-01", "2026-11-16")
    assert alice["totals"]["requests"] == 3
    assert alice["totals"]["input_tokens"] == 20
    assert alice["last_refreshed_at"] == "2026-11-16T12:00:00+00:00"
    assert alice["stale"] is True
    assert analytics_store.read("bob", "2026-11-01", "2026-11-16")["last_refreshed_at"] is None


def test_partial_snapshot_cannot_replace_previous_success(stored):
    analytics_store.publish("alice", rows(), "2026-11-01", "2026-11-16", [], "2026-11-16T12:00:00+00:00")
    with pytest.raises((ValueError, KeyError)):
        analytics_store.publish("alice", [{"day": "2026-11-15"}], "2026-11-01", "2026-11-16", [], "later")
    assert analytics_store.read("alice", "2026-11-01", "2026-11-16")["totals"]["requests"] == 3


@pytest.mark.asyncio
async def test_dashboard_read_never_fetches_upstream(stored):
    from app.routers.analytics import personal_analytics

    with patch.object(analytics, "refresh_user", AsyncMock()) as refresh:
        result = await personal_analytics(date(2026, 11, 1), date(2026, 11, 16), CurrentUser(user_id="bob", email="b@example.invalid"))
    refresh.assert_not_awaited()
    assert result["last_refreshed_at"] is None
    assert result["totals"]["requests"] == 0


@pytest.mark.asyncio
async def test_aggregate_refresh_checks_tokens_and_retains_failure(stored):
    upstream = [
        {"date": "2026-11-15", "metrics": {"spend": 0.03, "api_requests": 3, "total_tokens": 30, "prompt_tokens": 20, "completion_tokens": 10}}
    ]
    with (
        patch.object(analytics.upstream, "daily_usage", AsyncMock(return_value=upstream)),
        patch.object(analytics.litellm, "list_user_keys", AsyncMock(return_value=[])),
    ):
        await analytics.refresh_user("alice", date(2026, 11, 16))
    result = analytics_store.read("alice", "2026-11-01", "2026-11-16")
    assert result["totals"]["output_tokens"] == 10
    assert result["last_refreshed_at"]
    with patch.object(analytics.upstream, "daily_usage", AsyncMock(side_effect=HTTPException(502, "private upstream response"))):
        await analytics.refresh_user("alice", date(2026, 11, 16))
    result = analytics_store.read("alice", "2026-11-01", "2026-11-16")
    assert result["totals"]["requests"] == 3
    assert result["stale"] is True
    assert "private upstream response" not in str(result)


def test_missing_token_split_is_unavailable_not_zero(stored):
    values = analytics.normalize([{"date": "2026-11-15", "metrics": {"spend": 0, "api_requests": 1, "total_tokens": 8}}])
    assert values[0]["input_tokens"] is None
    assert values[0]["output_tokens"] is None


def test_first_refresh_failure_is_distinct_from_waiting_for_first_refresh(stored):
    assert analytics_store.read("alice", "2026-11-01", "2026-11-16")["refresh_failed"] is False
    analytics_store.failed("alice")
    result = analytics_store.read("alice", "2026-11-01", "2026-11-16")
    assert result["refresh_failed"] is True
    assert result["available"] is False
    assert result["last_refreshed_at"] is None


@pytest.mark.asyncio
async def test_hourly_schedule_accounts_for_work_duration_and_cancels_cleanly(monkeypatch):
    import asyncio

    waits = []

    async def stop(seconds):
        waits.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(analytics, "refresh_all", AsyncMock())
    monkeypatch.setattr(analytics.asyncio, "sleep", stop)
    moments = iter([100, 130])
    monkeypatch.setattr(analytics, "monotonic", lambda: next(moments))
    with pytest.raises(asyncio.CancelledError):
        await analytics.run()
    assert waits == [3570]


@pytest.mark.asyncio
async def test_early_end_date_is_validation_error_instead_of_calendar_underflow(stored):
    from app.routers.analytics import personal_analytics

    with pytest.raises(HTTPException) as invalid:
        await personal_analytics(None, date.min, CurrentUser(user_id="alice", email="alice@example.invalid"))
    assert invalid.value.status_code == 422


def test_concurrent_publication_cannot_mix_rows_with_old_freshness_or_budgets(stored, monkeypatch):
    analytics_store.publish("alice", rows(), "2026-11-01", "2026-11-16", [{"used": 3}], "2026-11-16T10:00:00+00:00")
    original = analytics_store.connect
    wrapped = False

    class Interleave:
        def __init__(self):
            self.db = original()

        def __enter__(self):
            self.db.__enter__()
            return self

        def __exit__(self, *args):
            return self.db.__exit__(*args)

        def execute(self, sql, parameters=()):
            if sql.startswith("SELECT failed_at"):
                newer = [{**rows()[0], "requests": 9, "cost": 0.09}]
                analytics_store.publish("alice", newer, "2026-11-01", "2026-11-16", [{"used": 9}], "2026-11-16T11:00:00+00:00")
            return self.db.execute(sql, parameters)

    def connection():
        nonlocal wrapped
        if not wrapped:
            wrapped = True
            return Interleave()
        return original()

    monkeypatch.setattr(analytics_store, "connect", connection)
    result = analytics_store.read("alice", "2026-11-01", "2026-11-16")
    assert result["totals"]["requests"] == result["budgets"][0]["used"] == 3
    assert result["last_refreshed_at"] == "2026-11-16T10:00:00+00:00"
    assert analytics_store.read("alice", "2026-11-01", "2026-11-16")["totals"]["requests"] == 9
