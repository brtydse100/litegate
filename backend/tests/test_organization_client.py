"""Verify native HTTP payloads and failure behavior at the LiteLLM boundary."""

import json
from unittest.mock import AsyncMock

from fastapi import HTTPException
import httpx
import pytest
import respx

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, organization_client as upstream
from tests.test_organization_config import example


@pytest.mark.asyncio
async def test_member_budget_patch_leaves_the_active_reset_window_untouched(monkeypatch):
    node = OrganizationHierarchy.model_validate(example()).resolve("u", ["squad1"])
    old = {
        "user_id": "u",
        "spend": 42,
        "litellm_budget_table": {"max_budget": 50, "budget_duration": "30d", "budget_reset_at": "2026-11-01T00:00:00Z"},
    }
    new = {**old, "litellm_budget_table": {**old["litellm_budget_table"], "max_budget": 100}}
    with respx.mock() as mock:
        patch = mock.post(settings.litellm_url + "/team/member_update").mock(return_value=httpx.Response(200, json={}))
        info = mock.get(settings.litellm_url + "/team/info").mock(return_value=httpx.Response(200, json={"team_memberships": [new]}))
        await upstream.sync_member(node, "u", {"team_memberships": [old]})
    assert json.loads(patch.calls[0].request.content) == {"team_id": "engineering", "user_id": "u", "max_budget_in_team": 100}
    assert info.calls[0].request.url.params["key_limit"] == "1"


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
async def test_upstream_errors_are_sanitized(response):
    with respx.mock() as mock:
        mock.get(settings.litellm_url + "/team/info").mock(return_value=response)
        with pytest.raises(HTTPException) as exc:
            await upstream.team_info("engineering")
    assert exc.value.status_code == 502
    assert "provider-secret" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_transport_failure_is_an_explicit_availability_error():
    with respx.mock() as mock:
        mock.get(settings.litellm_url + "/team/info").mock(side_effect=httpx.ConnectError("connection refused"))
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
