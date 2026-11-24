"""Bulk LiteLLM snapshots for reports and the organization sweep schedule."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import litellm, litellm_snapshot, organization_client as upstream, organization_reports as reports
from app.services import organization_sync as sync
from tests.test_budget_enforcement import org  # noqa: F401 - fixture


def use_bulk_listings(monkeypatch):
    monkeypatch.setattr(litellm_snapshot.teams, "_load", litellm_snapshot.load_teams)
    monkeypatch.setattr(litellm_snapshot.keys_by_user, "_load", litellm_snapshot._load_keys)


def team_page(teams, page=1, total_pages=1):
    return {"teams": teams, "total": len(teams), "page": page, "page_size": 100, "total_pages": total_pages}


@pytest.mark.asyncio
async def test_overview_reads_every_group_from_one_team_listing(org, monkeypatch):
    org()
    use_bulk_listings(monkeypatch)
    listed = [
        {"team_id": node.team_id, "spend": 3, "max_budget": None, "budget_duration": node.duration}
        for node in settings.organization_hierarchy.nodes.values()
    ]
    listing = AsyncMock(return_value=team_page(listed))
    monkeypatch.setattr(litellm, "list_teams", listing)
    team_info = AsyncMock(side_effect=AssertionError("per-team reads are not needed"))
    monkeypatch.setattr(upstream, "team_info", team_info)
    first = await reports.overview()
    await reports.overview()
    assert listing.await_count == 1
    assert team_info.await_count == 0
    assert all(group["group_spend"] is not None for group in first["groups"])
    assert all(group["sync_error"] is None for group in first["groups"])


@pytest.mark.asyncio
async def test_overview_falls_back_for_teams_missing_from_the_listing(org, monkeypatch):
    hierarchy = org()
    use_bulk_listings(monkeypatch)
    nodes = list(hierarchy.nodes.values())
    listed = [{"team_id": nodes[0].team_id, "spend": 1, "max_budget": None, "budget_duration": nodes[0].duration}]
    # The second team is listed without spend, as an older LiteLLM might.
    listed.append({"team_id": nodes[1].team_id})
    monkeypatch.setattr(litellm, "list_teams", AsyncMock(return_value=team_page(listed)))
    info = AsyncMock(return_value={"team_info": {"max_budget": None, "budget_duration": None, "spend": 2}})
    monkeypatch.setattr(upstream, "team_info", info)
    await reports.overview()
    asked = {call.args[0] for call in info.await_args_list}
    assert nodes[0].team_id not in asked
    assert nodes[1].team_id in asked


@pytest.mark.asyncio
async def test_concurrent_readers_share_one_refresh(monkeypatch):
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"team": {"team_id": "team"}}

    monkeypatch.setattr(litellm_snapshot.teams, "_load", load)
    results = await asyncio.gather(*(litellm_snapshot.teams.get() for _ in range(10)))
    assert calls == 1
    assert all(result == results[0] for result in results)


@pytest.mark.asyncio
async def test_a_failed_refresh_is_remembered_until_the_ttl_expires(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(litellm_snapshot, "monotonic", lambda: now[0])
    load = AsyncMock(side_effect=[HTTPException(status_code=503, detail="down"), {"ok": {}}])
    monkeypatch.setattr(litellm_snapshot.teams, "_load", load)
    for _ in range(3):
        with pytest.raises(HTTPException):
            await litellm_snapshot.teams.get()
    assert load.await_count == 1
    now[0] += litellm_snapshot.TTL
    assert await litellm_snapshot.teams.get() == {"ok": {}}
    assert load.await_count == 2


@pytest.mark.asyncio
async def test_a_malformed_listing_is_cached_as_an_upstream_failure(monkeypatch):
    load = AsyncMock(side_effect=ValueError("not json"))
    monkeypatch.setattr(litellm_snapshot.teams, "_load", load)
    errors = []
    for _ in range(2):
        with pytest.raises(HTTPException) as raised:
            await litellm_snapshot.teams.get()
        errors.append(raised.value)
    assert {error.status_code for error in errors} == {502}
    assert errors[0] is not errors[1]
    assert load.await_count == 1


@pytest.mark.asyncio
async def test_keys_repeated_across_pages_are_counted_once(monkeypatch):
    pages = {
        1: {"keys": [{"token": "a", "user_id": "ann", "spend": 1}], "total_pages": 2},
        2: {"keys": [{"token": "a", "user_id": "ann", "spend": 1}, {"token": "b", "user_id": "ann", "spend": 2}], "total_pages": 2},
    }
    monkeypatch.setattr(litellm, "list_keys", AsyncMock(side_effect=lambda page, size: pages[page]))
    owners = await litellm_snapshot._load_keys()
    assert [key["token"] for key in owners["ann"]] == ["a", "b"]


@pytest.mark.asyncio
async def test_team_listing_beyond_its_page_bound_fails_closed(monkeypatch):
    monkeypatch.setattr(litellm_snapshot, "TEAM_PAGES", 2)
    listing = AsyncMock(return_value=team_page([], total_pages=3))
    monkeypatch.setattr(litellm, "list_teams", listing)
    with pytest.raises(HTTPException) as raised:
        await litellm_snapshot.load_teams()
    assert raised.value.status_code == 409
    assert listing.await_count == 1


@pytest.mark.asyncio
async def test_reports_with_nothing_to_show_skip_the_listings(org, monkeypatch):
    org()
    teams = AsyncMock(side_effect=AssertionError("team listing not needed"))
    keys = AsyncMock(side_effect=AssertionError("key listing not needed"))
    monkeypatch.setattr(litellm_snapshot.teams, "get", teams)
    monkeypatch.setattr(litellm_snapshot.keys_by_user, "get", keys)
    empty_page = await reports.users(None, 999, 25)
    assert empty_page["users"] == []
    nothing_visible = reports.OrganizationScope(roots=())
    assert (await reports.overview(nothing_visible))["groups"] == []
    assert teams.await_count == keys.await_count == 0


@pytest.mark.asyncio
async def test_concurrent_waiters_share_one_failed_refresh(monkeypatch):
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        raise HTTPException(status_code=503, detail="down")

    monkeypatch.setattr(litellm_snapshot.teams, "_load", load)
    results = await asyncio.gather(*(litellm_snapshot.teams.get() for _ in range(10)), return_exceptions=True)
    assert calls == 1
    assert all(isinstance(result, HTTPException) for result in results)


@pytest.mark.asyncio
async def test_listing_beyond_the_page_bound_fails_closed_on_the_first_page(monkeypatch):
    monkeypatch.setattr(litellm_snapshot, "KEY_PAGES", 2)
    listing = AsyncMock(return_value={"keys": [], "total_pages": 3})
    monkeypatch.setattr(litellm, "list_keys", listing)
    with pytest.raises(HTTPException) as raised:
        await litellm_snapshot._load_keys()
    assert raised.value.status_code == 409
    assert listing.await_count == 1


@pytest.mark.asyncio
async def test_listed_teams_without_budget_fields_fall_back_to_team_info(org, monkeypatch):
    hierarchy = org()
    use_bulk_listings(monkeypatch)
    node = next(iter(hierarchy.nodes.values()))
    # Spend alone is not enough: a missing duration must not read as a mismatch.
    monkeypatch.setattr(litellm, "list_teams", AsyncMock(return_value=team_page([{"team_id": node.team_id, "spend": 1}])))
    info = AsyncMock(return_value={"team_info": {"max_budget": None, "budget_duration": node.duration, "spend": 1}})
    monkeypatch.setattr(upstream, "team_info", info)
    result = await reports.overview()
    assert node.team_id in {call.args[0] for call in info.await_args_list}
    assert next(group for group in result["groups"] if group["id"] == node.id)["sync_error"] is None


@pytest.mark.asyncio
async def test_users_page_reads_spend_from_one_key_listing(org, monkeypatch):
    org()
    use_bulk_listings(monkeypatch)
    keys = [
        {"token": "a1", "user_id": "ann", "spend": 4},
        {"token": "a2", "user_id": "ann", "spend": 1},
        {"token": "b1", "user_id": "ben", "spend": 2},
        {"token": "x", "user_id": None, "spend": 99},
    ]
    listing = AsyncMock(return_value={"keys": keys, "total_pages": 1})
    monkeypatch.setattr(litellm, "list_keys", listing)
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(side_effect=AssertionError("per-user reads are not needed")))
    first = await reports.users(None, 1, 25)
    await reports.users(None, 1, 25)
    spend = {user["user_id"]: user["budget_spend"] for user in first["users"]}
    assert spend["ann"] == 5
    assert spend["ben"] == 2
    assert spend["cat"] == 0
    assert listing.await_count == 1


@pytest.mark.asyncio
async def test_users_page_falls_back_to_per_user_reads_without_a_listing(org, monkeypatch):
    org()
    per_user = AsyncMock(return_value=[{"spend": 3}])
    monkeypatch.setattr(litellm, "list_user_keys", per_user)
    result = await reports.users(None, 1, 25)
    assert per_user.await_count == len(result["users"])
    assert {user["budget_spend"] for user in result["users"]} == {3}


@pytest.mark.asyncio
async def test_sweep_waits_for_the_configured_interval(monkeypatch):
    monkeypatch.setattr(settings, "organization_sync_interval_seconds", 900)
    attempt = AsyncMock()
    monkeypatch.setattr(sync, "reconciliation_attempt", attempt)
    sleeps, timeouts = [], []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise asyncio.CancelledError

    async def wait_for(awaitable, timeout):
        timeouts.append(timeout)
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(sync.asyncio, "sleep", sleep)
    monkeypatch.setattr(sync.asyncio, "wait_for", wait_for)
    with pytest.raises(asyncio.CancelledError):
        await sync.run_reconciliation()
    assert sleeps == [60, 60]
    assert timeouts == [840]
    attempt.assert_awaited_once()


@pytest.mark.asyncio
async def test_budget_edits_wake_the_sweep_early(monkeypatch):
    monkeypatch.setattr(settings, "organization_sync_interval_seconds", 86_400)
    monkeypatch.setattr(sync, "MIN_PASS_SPACING", 0)
    ran = asyncio.Event()

    async def attempt():
        ran.set()

    monkeypatch.setattr(sync, "reconciliation_attempt", attempt)
    loop = asyncio.create_task(sync.run_reconciliation())
    try:
        await asyncio.sleep(0.01)
        assert not ran.is_set()
        sync.request_reconciliation()
        await asyncio.wait_for(ran.wait(), timeout=1)
    finally:
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["failed", "unverified"])
async def test_a_failed_or_unverified_pass_retries_after_the_spacing(org, monkeypatch, cause):
    org()
    monkeypatch.setattr(settings, "organization_sync_interval_seconds", 900)
    monkeypatch.setattr(sync.budget_pass, "cross_group_pending", lambda: cause == "unverified")
    monkeypatch.setattr(sync, "reconciliation_attempt", AsyncMock(return_value=cause != "failed"))
    timeouts = []

    async def sleep(seconds):
        if len(timeouts) == 6:
            raise asyncio.CancelledError

    async def wait_for(awaitable, timeout):
        timeouts.append(timeout)
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(sync.asyncio, "sleep", sleep)
    monkeypatch.setattr(sync.asyncio, "wait_for", wait_for)
    with pytest.raises(asyncio.CancelledError):
        await sync.run_reconciliation()
    # Retries start a minute apart and double up to the interval. The first
    # wait follows a successful startup pass in the failed case.
    backoff = [0, 60, 180, 420, 840]
    assert timeouts == ([840, *backoff] if cause == "failed" else [*backoff, 840])


@pytest.mark.asyncio
async def test_a_failed_startup_pass_retries_after_a_minute_and_success_resets(monkeypatch):
    monkeypatch.setattr(settings, "organization_sync_interval_seconds", 900)
    monkeypatch.setattr(sync, "reconciliation_attempt", AsyncMock(side_effect=[False, True, True]))
    timeouts = []

    async def sleep(seconds):
        if len(timeouts) == 3:
            raise asyncio.CancelledError

    async def wait_for(awaitable, timeout):
        timeouts.append(timeout)
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(sync.asyncio, "sleep", sleep)
    monkeypatch.setattr(sync.asyncio, "wait_for", wait_for)
    with pytest.raises(asyncio.CancelledError):
        await sync.run_reconciliation(failed=True)
    assert timeouts == [0, 60, 840]


@pytest.mark.asyncio
async def test_without_a_hierarchy_unverified_state_keeps_the_full_interval(monkeypatch):
    monkeypatch.setattr(settings, "organization_sync_interval_seconds", 900)
    monkeypatch.setattr(sync.budget_pass, "cross_group_pending", lambda: True)
    monkeypatch.setattr(sync, "reconciliation_attempt", AsyncMock(return_value=True))
    timeouts = []

    async def sleep(seconds):
        if timeouts:
            raise asyncio.CancelledError

    async def wait_for(awaitable, timeout):
        timeouts.append(timeout)
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(sync.asyncio, "sleep", sleep)
    monkeypatch.setattr(sync.asyncio, "wait_for", wait_for)
    with pytest.raises(asyncio.CancelledError):
        await sync.run_reconciliation()
    assert timeouts == [840]


@pytest.mark.asyncio
async def test_an_edit_during_a_pass_triggers_exactly_one_more_pass(monkeypatch):
    monkeypatch.setattr(settings, "organization_sync_interval_seconds", 86_400)
    monkeypatch.setattr(sync, "MIN_PASS_SPACING", 0)
    passes = 0

    async def attempt():
        nonlocal passes
        passes += 1
        if passes == 1:
            sync.request_reconciliation()  # an edit lands while this pass runs

    monkeypatch.setattr(sync, "reconciliation_attempt", attempt)
    loop = asyncio.create_task(sync.run_reconciliation())
    try:
        await asyncio.sleep(0.01)
        sync.request_reconciliation()
        for _ in range(50):
            await asyncio.sleep(0.01)
        assert passes == 2
    finally:
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)
