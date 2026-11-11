from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.models import BulkKeyUpdateRequest, CurrentUser, TeamCreateRequest, TeamUpdateRequest
from app.rate_limit import _key_ops
from app.routers.api_actor import ApiActor
from app.routers.api_v1 import api_create_team, api_update_team, bulk_update_keys
from app.routers.api_v1_policy_schemas import api_policy_schemas
from app.services import policy_schemas
from tests.test_policy_schemas import document, nested_document


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.setattr(policy_schemas, "_cache", None)
    _key_ops.clear()


def admin():
    return ApiActor(CurrentUser(user_id="admin", email="a@example.com", role="admin"))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 500])
async def test_unavailable_upstream_is_safe_and_negative_cached(status):
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(status, json={"secret": "hidden-upstream-value"})

    @asynccontextmanager
    async def transport():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as upstream:
            yield upstream

    with patch.object(policy_schemas, "client", transport):
        first = await policy_schemas.get_policy_schemas()
        assert await policy_schemas.get_policy_schemas() == first
    assert len(requests) == 1
    assert first["available"] is False
    assert first["schemas"] == {}
    assert "hidden-upstream-value" not in str(first)


@pytest.mark.asyncio
async def test_discovery_uses_only_configured_origin_no_redirect_or_external_ref_fetch(monkeypatch):
    monkeypatch.setattr(settings, "litellm_url", "https://configured.invalid/prefix/")
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(200, json=document({"policy": {"$ref": "https://evil.invalid/schema"}}))

    @asynccontextmanager
    async def transport():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as upstream:
            yield upstream

    with patch.object(policy_schemas, "client", transport):
        assert (await policy_schemas.get_policy_schemas())["available"] is False
    assert [str(request.url) for request in requests] == ["https://configured.invalid/prefix/openapi.json"]


@pytest.mark.asyncio
async def test_redirect_is_not_followed():
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://evil.invalid/schema"})

    @asynccontextmanager
    async def transport():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as upstream:
            yield upstream

    with patch.object(policy_schemas, "client", transport):
        assert (await policy_schemas.get_policy_schemas())["available"] is False
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_size_limit_and_timeout_fail_closed(monkeypatch):
    monkeypatch.setattr(policy_schemas, "MAX_DOCUMENT_BYTES", 10)

    @asynccontextmanager
    async def transport():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b" " * 11))) as upstream:
            yield upstream

    with patch.object(policy_schemas, "client", transport):
        assert (await policy_schemas.get_policy_schemas())["available"] is False
    monkeypatch.setattr(policy_schemas, "_cache", None)
    with patch.object(policy_schemas, "_fetch_schemas", AsyncMock(side_effect=httpx.ReadTimeout("hidden-upstream-value"))):
        result = await policy_schemas.get_policy_schemas()
        assert result["available"] is False
        assert "hidden-upstream-value" not in str(result)


@pytest.mark.asyncio
async def test_cache_expiry_copy_and_origin_change(monkeypatch):
    discovery = {"available": True, "schemas": policy_schemas.extract_schemas(document({"new_policy": {"type": "boolean"}}))}
    with patch.object(policy_schemas, "_fetch_schemas", AsyncMock(return_value=discovery)) as fetch:
        first = await policy_schemas.get_policy_schemas()
        first["schemas"].clear()
        assert (await policy_schemas.get_policy_schemas())["schemas"]
        assert fetch.await_count == 1
        monkeypatch.setattr(settings, "litellm_url", "https://another.invalid")
        assert (await policy_schemas.get_policy_schemas())["available"]
        assert fetch.await_count == 2
        monkeypatch.setattr(policy_schemas.time, "monotonic", lambda: 1e20)
        await policy_schemas.get_policy_schemas()
        assert fetch.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor",
    [
        ApiActor(CurrentUser(user_id="u", email="u@example.com")),
        ApiActor(CurrentUser(user_id="k", email="", auth_source="litellm_key"), proof_key="credential"),
    ],
)
async def test_nonadmins_cannot_discover_schemas(actor):
    with patch("app.routers.api_v1_policy_schemas.get_policy_schemas", AsyncMock()) as fetch, pytest.raises(HTTPException) as exc:
        await api_policy_schemas(actor)
    assert exc.value.status_code == 403
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_advanced_permodel_budget_enterprise_gate_and_actual_payload(monkeypatch):
    discovery = {"available": True, "schemas": policy_schemas.extract_schemas(nested_document())}
    budget = {"model-a": {"budget_limit": 3, "time_period": "1d"}}
    payload = BulkKeyUpdateRequest(keys=["key-id"], settings={"advanced_settings": {"model_max_budget": budget}})
    with (
        patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value=discovery)),
        patch("app.routers.api_v1.organization_sync.guard_key", AsyncMock()) as guard,
        patch("app.routers.api_v1.key_budgets.update_key", AsyncMock(return_value={})) as update,
        patch("app.routers.api_v1._record_audit", AsyncMock()) as audit,
    ):
        monkeypatch.setattr(settings, "litellm_enterprise_enabled", False)
        with pytest.raises(HTTPException) as exc:
            await bulk_update_keys(payload, admin())
        assert exc.value.status_code == 403
        update.assert_not_awaited()
        monkeypatch.setattr(settings, "litellm_enterprise_enabled", True)
        result = await bulk_update_keys(payload, admin())
        assert result["updated"] == 1
        guard.assert_awaited_once_with("key-id", {"model_max_budget": budget}, use_key_budget_only=False)
        update.assert_awaited_once_with("key-id", {"model_max_budget": budget}, use_key_budget_only=False)
        assert audit.await_args.kwargs["details"]["setting_fields"] == ["model_max_budget"]
        assert "model-a" not in str(audit.await_args.kwargs)


@pytest.mark.asyncio
async def test_dynamic_team_policy_merge_precedes_guard_and_upstream_mutation():
    fields = {
        "team_member_budget": {"type": "number"},
        "object_permission": nested_document()["paths"]["/team/update"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"][
            "object_permission"
        ],
    }
    data = document(fields)
    data["components"] = nested_document()["components"]
    discovery = {"available": True, "schemas": policy_schemas.extract_schemas(data)}
    values = {"team_member_budget": 10, "object_permission": {"mcp_servers": ["server-1"]}}
    events = []

    def guard(team_id, changes):
        events.append("guard")
        assert changes == values
        raise HTTPException(status_code=409, detail="Managed policy")

    with (
        patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value=discovery)),
        patch("app.routers.api_v1.organization_sync.guard_team", side_effect=guard),
        patch("app.routers.api_v1.llm.update_team", AsyncMock()) as update,
    ):
        with pytest.raises(HTTPException) as exc:
            await api_update_team("team-id", TeamUpdateRequest(advanced_settings=values), admin())
        assert exc.value.status_code == 409
        update.assert_not_awaited()
    with (
        patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value=discovery)),
        patch("app.routers.api_v1.llm.create_team", AsyncMock(return_value={"team_id": "new-team"})) as create,
        patch("app.routers.api_v1._record_audit", AsyncMock()) as audit,
    ):
        await api_create_team(TeamCreateRequest(team_alias="New", advanced_settings=values), admin())
        assert create.await_args.args[0] == {"team_alias": "New", "models": [], "blocked": False, **values}
        assert set(audit.await_args.kwargs["details"]["setting_fields"]) == {"team_alias", "models", "blocked", *values}


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", [{"type": "not-a-real-type", "properties": {}}, {"type": "object", "properties": []}])
async def test_malformed_upstream_schema_is_unavailable(schema):
    data = document({})
    data["paths"]["/key/update"]["post"]["requestBody"]["content"]["application/json"]["schema"] = schema

    @asynccontextmanager
    async def transport():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))) as upstream:
            yield upstream

    with patch.object(policy_schemas, "client", transport):
        assert (await policy_schemas.get_policy_schemas())["available"] is False
