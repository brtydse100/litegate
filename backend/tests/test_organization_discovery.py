"""Operator email assignments never establish login identity or replace credentials."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, local_users, organization_discovery as discovery
from app.services import organization_sync as sync, organization_store as store, organization_client as upstream
from app.services import organization_key_policy as key_policy

REAL_REQUEST = upstream.request


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "users.db"))
    configure(monkeypatch, ["alice@example.com"])
    local_users.init_db()
    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"max_budget": None}, "team_memberships": []}))
    monkeypatch.setattr(key_policy, "finish_team", AsyncMock())
    monkeypatch.setattr(key_policy, "normalize_individual_caps", AsyncMock())
    monkeypatch.setattr(litellm, "add_team_member", AsyncMock())
    monkeypatch.setattr(litellm, "get_user", AsyncMock(side_effect=lambda uid: {"user_info": user()} if uid == "subject" else None))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value=page([user()])))
    monkeypatch.setattr(litellm, "generate_key", AsyncMock(side_effect=AssertionError("no generation")))
    monkeypatch.setattr(litellm, "create_user", AsyncMock(side_effect=AssertionError("no creation")))
    monkeypatch.setattr(litellm, "delete_key", AsyncMock(side_effect=AssertionError("no deletion")))


def configure(monkeypatch, selectors):
    monkeypatch.setattr(
        settings,
        "organization_hierarchy",
        OrganizationHierarchy.model_validate(
            {
                "levels": [
                    {
                        "name": "Division",
                        "groups": [
                            {
                                "members": [
                                    {
                                        "name": "Engineering",
                                        "litellmTeamId": "engineering",
                                        "userIds": selectors,
                                        "budget": {"perUser": 100, "duration": "30d"},
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        ),
    )


def user(uid="subject", email="Alice@Example.COM", **kwargs):
    return {"user_id": uid, "user_email": email, **kwargs}


def page(users, number=1, total=None):
    total = len(users) if total is None else total
    return {"users": users, "page": number, "page_size": 100, "total": total, "total_pages": (total + 99) // 100}


@pytest.mark.asyncio
async def test_no_login_existing_email_migrates_same_key(monkeypatch):
    key = {"token": "synthetic-hash", "key_alias": "existing", "spend": 42, "models": ["model-a"], "team_id": "old"}
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[key]))
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"team_id": "engineering", "max_budget": 100, "budget_duration": "30d"}))
    await sync.reconcile()
    assert store.get("subject")["auth_source"] == "configured_email"
    assert store.get("subject")["team_id"] == "engineering"
    update.assert_awaited_once_with("synthetic-hash", {"team_id": "engineering", "max_budget": 100.0, "budget_duration": "30d"})
    assert key["spend"] == 42 and key["models"] == ["model-a"] and key["key_alias"] == "existing"
    litellm.generate_key.assert_not_awaited()
    litellm.create_user.assert_not_awaited()
    litellm.delete_key.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_pages_exact_normalized_match(monkeypatch):
    first = [user(f"a{i:03}", "prefix-alice@example.com") for i in range(100)]
    request = AsyncMock(side_effect=[page(first, total=101), page([user()], 2, 101)])
    monkeypatch.setattr(upstream, "request", request)
    assert (await discovery.email_match("alice@example.com"))["user_id"] == "subject"
    assert request.call_args_list[1].kwargs["params"]["page"] == 2
    assert request.call_args.kwargs["params"]["sort_by"] == "user_id"


@pytest.mark.asyncio
async def test_duplicate_exact_on_later_page_rejected(monkeypatch):
    first = [user()] + [user(f"z{i}", "prefix-alice@example.com") for i in range(99)]
    monkeypatch.setattr(upstream, "request", AsyncMock(side_effect=[page(first, total=101), page([user("other")], 2, 101)]))
    with pytest.raises(HTTPException, match="multiple"):
        await discovery.email_match("alice@example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"users": []},
        page([], total=1),
        page([{}]),
        page([user(), user()]),
        {**page([user()]), "total_pages": 101},
        {**page([user()]), "page": 2},
    ],
)
async def test_malformed_and_incomplete_rejected(monkeypatch, data):
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value=data))
    with pytest.raises(HTTPException):
        await discovery.email_match("alice@example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["changed", "ambiguous", "transport", "removed", "missing", "incomplete"])
async def test_every_pass_invalidates_stale_assignment_before_writes(monkeypatch, failure):
    await sync.reconcile()
    assert store.get("subject")["sync_error"] is None
    write = AsyncMock()
    monkeypatch.setattr(sync, "sync_identity", write)
    if failure == "changed":
        monkeypatch.setattr(
            litellm, "get_user", AsyncMock(side_effect=lambda uid: {"user_info": user(email="new@example.com")} if uid == "subject" else None)
        )
    elif failure == "ambiguous":
        monkeypatch.setattr(upstream, "request", AsyncMock(return_value=page([user(), user("other")])))
    elif failure == "transport":
        monkeypatch.setattr(upstream, "request", AsyncMock(side_effect=HTTPException(502, "transport unavailable")))
    elif failure == "removed":
        configure(monkeypatch, [])
    elif failure == "incomplete":
        monkeypatch.setattr(upstream, "request", AsyncMock(return_value=page([], total=1)))
    else:
        monkeypatch.setattr(upstream, "request", AsyncMock(return_value=page([])))
    await sync.reconcile()
    write.assert_not_awaited()
    assert store.get("subject")["sync_error"]
    with pytest.raises(HTTPException):
        sync.resolve_identity(store.get("subject"))


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["proxy_admin", "proxy_admin_viewer", "org_admin"])
async def test_email_only_admin_rejected(monkeypatch, role):
    monkeypatch.setattr(litellm, "get_user", AsyncMock(side_effect=lambda uid: {"user_info": user(user_role=role)} if uid == "subject" else None))
    await sync.reconcile()
    assert store.get("subject") is None


@pytest.mark.asyncio
async def test_email_local_collision_rejected():
    local_users.create_user("alice", "alice@example.com", "synthetic-password")
    await sync.reconcile()
    assert store.get("subject") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["sso", "local"])
async def test_verified_records_including_rejected_claims_never_overwritten(source):
    store.remember("subject", "other@example.com", source, ["rejected-group"])
    store.failed("subject", "old rejection")
    await sync.reconcile()
    identity = store.get("subject")
    assert (identity["email"], identity["auth_source"], identity["groups"]) == ("other@example.com", source, ["rejected-group"])
    assert identity["sync_error"]


@pytest.mark.asyncio
async def test_exact_at_id_precedes_email(monkeypatch):
    monkeypatch.setattr(litellm, "get_user", AsyncMock(side_effect=lambda uid: {"user_info": user(uid)}))
    await sync.reconcile()
    assert store.get("alice@example.com")["auth_source"] == "explicit"
    upstream.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_large_existing_batch_is_bounded_and_needs_no_callback(monkeypatch):
    selectors = [f"subject-{i}" for i in range(120)]
    configure(monkeypatch, selectors)
    active = peak = 0

    async def lookup(uid):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.001)
        active -= 1
        return {"user_info": user(uid)}

    monkeypatch.setattr(litellm, "get_user", lookup)
    await sync.reconcile()
    assert peak <= 5
    assert len(store.list_identities()) == 120
    assert all(identity["team_id"] == "engineering" for identity in store.list_identities())


@pytest.mark.asyncio
async def test_missing_users_skip_and_retry(monkeypatch):
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value=page([])))
    await sync.reconcile()
    assert store.list_identities() == []
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value=page([user()])))
    await sync.reconcile()
    assert store.get("subject")["team_id"] == "engineering"


@pytest.mark.asyncio
async def test_lifespan_awaits_first_attempt_then_retry_waits(monkeypatch):
    from app.main import app, lifespan

    order = []

    async def first():
        order.append("first")
        await asyncio.sleep(0)
        order.append("done")

    monkeypatch.setattr(sync, "reconciliation_attempt", first)
    monkeypatch.setattr(litellm, "start_client", AsyncMock())
    monkeypatch.setattr(litellm, "close_client", AsyncMock())
    async with lifespan(app):
        assert order == ["first", "done"]
        await asyncio.sleep(0)
        assert order == ["first", "done"]
    waits = []
    monkeypatch.setattr(sync, "reconciliation_attempt", AsyncMock())

    async def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(sync.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await sync.run_reconciliation()
    assert waits == [60, 60]
    sync.reconciliation_attempt.assert_awaited_once()


@pytest.mark.asyncio
async def test_changed_total_on_second_page_fails_closed(monkeypatch):
    first = [user(f"a{i}", "prefix-alice@example.com") for i in range(100)]
    monkeypatch.setattr(upstream, "request", AsyncMock(side_effect=[page(first, total=101), page([user(), user("other")], 2, 102)]))
    with pytest.raises(HTTPException, match="incomplete"):
        await discovery.email_match("alice@example.com")


@pytest.mark.asyncio
async def test_timeout_fails_closed_without_waiting_a_minute(monkeypatch):
    real_timeout = asyncio.timeout

    async def pending(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(discovery.asyncio, "timeout", lambda _: real_timeout(0.001))
    monkeypatch.setattr(upstream, "request", pending)
    with pytest.raises(HTTPException, match="timed out"):
        await discovery.email_match("alice@example.com")


@pytest.mark.asyncio
async def test_real_transport_failure_is_an_actionable_lookup_error(monkeypatch):
    import httpx

    def fail(request):
        raise httpx.ConnectError("synthetic outage", request=request)

    monkeypatch.setattr(upstream, "request", REAL_REQUEST)
    monkeypatch.setattr(upstream, "client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fail)))
    with pytest.raises(HTTPException) as exc:
        await discovery.email_match("alice@example.com")
    assert exc.value.status_code in {502, 503}


@pytest.mark.asyncio
async def test_email_and_exact_id_incompatible_paths_are_rejected(monkeypatch):
    values = settings.organization_hierarchy.model_dump()
    values["levels"][0]["groups"][0]["members"].append({"name": "Other", "litellmTeamId": "other", "userIds": ["subject"]})
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(values))
    await sync.reconcile()
    identity = store.get("subject")
    # Exact discovery records only the ID; its assignment stays authoritative.
    assert identity["auth_source"] == "explicit"
    assert identity["team_id"] == "other"


@pytest.mark.asyncio
async def test_rejected_sso_conflicting_email_path_stays_rejected(monkeypatch):
    values = settings.organization_hierarchy.model_dump()
    values["levels"][0]["groups"][0]["members"].append({"name": "Other", "litellmTeamId": "other", "ssoGroups": ["other"]})
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(values))
    store.remember("subject", "alice@example.com", "sso", ["other"])
    store.failed("subject", "conflict")
    await sync.reconcile()
    identity = store.get("subject")
    assert identity["auth_source"] == "sso" and identity["groups"] == ["other"]
    assert "conflict" in identity["sync_error"]
    assert identity["team_id"] is None


@pytest.mark.asyncio
async def test_inflight_revalidation_blocks_old_policy_even_if_pass_aborts(monkeypatch):
    await sync.reconcile()

    async def broken_lookup(uid):
        # Once validation starts, the old assignment cannot authorize writes.
        with pytest.raises(HTTPException):
            sync.resolve_identity(store.get("subject"))
        raise ValueError("invalid upstream JSON")

    monkeypatch.setattr(litellm, "get_user", broken_lookup)
    await sync.reconciliation_attempt()
    with pytest.raises(HTTPException):
        sync.resolve_identity(store.get("subject"))
