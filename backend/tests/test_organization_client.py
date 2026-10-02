"""Verify native HTTP payloads and failure behavior at the LiteLLM boundary."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from fastapi import HTTPException
import httpx
import pytest

from app.organization import OrganizationHierarchy
from app.services import litellm, organization_client as upstream
from tests.test_organization_config import example


def mock_http(monkeypatch, response):
    calls = []

    def handle(request):
        calls.append(request)
        if isinstance(response, Exception):
            raise response
        return response(request) if callable(response) else response

    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as pooled:
            yield pooled

    monkeypatch.setattr(upstream, "client", client)
    return calls


@pytest.mark.asyncio
async def test_member_budget_patch_leaves_the_active_reset_window_untouched(monkeypatch):
    node = OrganizationHierarchy.model_validate(example()).resolve("u", ["squad1"])
    old = {
        "user_id": "u",
        "spend": 42,
        "litellm_budget_table": {"max_budget": 50, "budget_duration": "30d", "budget_reset_at": "2026-11-01T00:00:00Z"},
    }
    new = {**old, "litellm_budget_table": {**old["litellm_budget_table"], "max_budget": 100}}

    def response(request):
        if request.method == "POST":
            assert request.url.path == "/team/member_update"
            return httpx.Response(200, json={})
        assert request.url.path == "/team/info"
        return httpx.Response(200, json={"team_memberships": [new]})

    calls = mock_http(monkeypatch, response)
    await upstream.sync_member(node, "u", {"team_memberships": [old]})
    assert json.loads(calls[0].content) == {"team_id": "engineering", "user_id": "u", "max_budget_in_team": 100}
    assert calls[1].url.params["key_limit"] == "1"


@pytest.mark.asyncio
async def test_ignored_member_fields_fail_verification_before_key_changes(monkeypatch):
    node = OrganizationHierarchy.model_validate(example()).resolve("u", ["squad1"])
    old = {"team_memberships": [{"user_id": "u", "litellm_budget_table": {"max_budget": 50, "budget_duration": "30d"}}]}
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=old))
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value={}))
    with pytest.raises(HTTPException, match="per-user budget") as exc:
        await upstream.sync_member(node, "u", old)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_ignored_root_budget_fields_fail_verification(monkeypatch):
    root = OrganizationHierarchy.model_validate(example()).roots[0]
    old = {"max_budget": 50, "budget_duration": "30d"}
    monkeypatch.setattr(litellm, "get_team", AsyncMock(return_value=old))
    monkeypatch.setattr(litellm, "update_team", AsyncMock())
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": old}))
    with pytest.raises(HTTPException, match="top-level budget"):
        await upstream.sync_root(root)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response", [httpx.Response(403, json={"secret": "provider-secret"}), httpx.Response(200, text="not json"), httpx.Response(200, json=[])]
)
async def test_upstream_errors_are_sanitized(monkeypatch, response):
    mock_http(monkeypatch, response)
    with pytest.raises(HTTPException) as exc:
        await upstream.team_info("engineering")
    assert exc.value.status_code == 502
    assert "provider-secret" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_transport_failure_is_an_explicit_availability_error(monkeypatch):
    mock_http(monkeypatch, httpx.ConnectError("connection refused"))
    with pytest.raises(HTTPException) as exc:
        await upstream.team_info("engineering")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_clearing_an_inherited_allowance_sends_explicit_null(monkeypatch):
    tree = OrganizationHierarchy.model_validate(example())
    node = tree.resolve("u", ["unlimited"])
    old = {"team_memberships": [{"user_id": "u", "litellm_budget_table": {"max_budget": 50, "budget_duration": "30d"}}]}
    patch = AsyncMock(return_value={})
    monkeypatch.setattr(upstream, "request", patch)
    monkeypatch.setattr(
        upstream, "team_info", AsyncMock(return_value={"team_memberships": [{"user_id": "u", "litellm_budget_table": {"budget_duration": "30d"}}]})
    )
    await upstream.sync_member(node, "u", old)
    assert patch.call_args.kwargs["payload"] == {"team_id": "engineering", "user_id": "u", "max_budget_in_team": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("write_needed", [False, True])
async def test_null_allowance_cannot_pass_with_a_finite_team_default(monkeypatch, write_needed):
    node = OrganizationHierarchy.model_validate(example()).resolve("u", ["unlimited"])
    info = {
        "team_info": {"metadata": {"team_member_budget_id": "default"}, "team_member_budget_table": {"max_budget": 50}},
        "team_memberships": [{"user_id": "u", "spend": 60, "litellm_budget_table": {"max_budget": None, "budget_duration": "30d"}}],
    }
    old = {**info, "team_memberships": [{"user_id": "u", "litellm_budget_table": {"max_budget": 100}}]} if write_needed else info
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=info))
    with pytest.raises(HTTPException, match="per-user budget"):
        await upstream.sync_member(node, "u", old)


@pytest.mark.asyncio
@pytest.mark.parametrize("applied", [True, False])
async def test_root_sync_clears_and_verifies_only_the_default_member_cap(monkeypatch, applied):
    root = OrganizationHierarchy.model_validate(example()).roots[0]
    team = {"max_budget": 5000, "budget_duration": "30d", "metadata": {"team_member_budget_id": "default"}}
    original = {"team_info": {**team, "team_member_budget_table": {"max_budget": 50, "rpm_limit": 10}}}
    verified = {"team_info": {**team, "team_member_budget_table": {"max_budget": None, "rpm_limit": 10}}} if applied else original
    update = AsyncMock()
    monkeypatch.setattr(litellm, "get_team", AsyncMock(return_value=team))
    monkeypatch.setattr(litellm, "update_team", update)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(side_effect=[original, verified]))
    if applied:
        result = await upstream.sync_root(root)
        assert result["team_info"]["team_member_budget_table"]["rpm_limit"] == 10
    else:
        with pytest.raises(HTTPException, match="default member budget"):
            await upstream.sync_root(root)
    update.assert_awaited_once_with("engineering", {"team_member_budget": None})
