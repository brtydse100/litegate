from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models import KeySettingsUpdate
from app.services import policy_schemas


def document(properties):
    schema = {"type": "object", "properties": properties, "required": ["key"]}
    return {
        "openapi": "3.1.0",
        "paths": {
            path: {"post": {"requestBody": {"content": {"application/json": {"schema": schema}}}}}
            for path in ["/key/update", "/team/new", "/team/update"]
        },
    }


def test_discovers_new_policy_and_filters_credentials_defaults_and_identity():
    schemas = policy_schemas.extract_schemas(
        document(
            {
                "key": {"type": "string"},
                "user_id": {"type": "string"},
                "new_policy": {"type": "integer", "minimum": 1, "default": 2},
                "api_key": {"type": "string"},
                "private": {"type": "string", "writeOnly": True},
                "models": {"type": "array", "items": {"type": "string"}},
            }
        )
    )
    assert schemas["key_update"]["properties"] == {
        "new_policy": {"type": "integer", "minimum": 1},
        "models": {"type": "array", "items": {"type": "string"}},
    }
    assert "key" not in schemas["key_update"].get("required", [])


@pytest.mark.asyncio
async def test_advanced_values_validate_and_merge_without_code_change():
    schemas = policy_schemas.extract_schemas(document({"new_policy": {"type": "integer", "minimum": 1}}))
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value={"available": True, "schemas": schemas})):
        assert await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"new_policy": 3})) == {"new_policy": 3}
        with pytest.raises(HTTPException) as exc:
            await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"new_policy": "secret-value"}))
        assert exc.value.status_code == 422
        assert "secret-value" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_discovery_denies_even_admin_role_litellm_key_proof():
    from app.models import CurrentUser
    from app.routers.api_actor import ApiActor
    from app.routers.api_v1_policy_schemas import api_policy_schemas

    actor = ApiActor(CurrentUser(user_id="holder", email="", role="admin", auth_source="litellm_key"), proof_key="credential")
    with pytest.raises(HTTPException) as exc:
        await api_policy_schemas(actor)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_nonfinite_advanced_numbers_rejected():
    schemas = policy_schemas.extract_schemas(document({"new_policy": {"type": "number"}}))
    with (
        patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value={"available": True, "schemas": schemas})),
        pytest.raises(HTTPException) as exc,
    ):
        await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"new_policy": float("nan")}))
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "name", ["auto_rotate", "rotation_interval", "agent_id", "spend", "members_with_roles", "budget_id", "team_id", "organization_id"]
)
def test_dedicated_workflow_fields_never_advertised(name):
    schema = policy_schemas.extract_schemas(document({name: {"type": "string"}}))
    assert name not in schema["key_update"]["properties"]


def nested_document():
    data = document(
        {
            "object_permission": {"anyOf": [{"$ref": "#/components/schemas/Permission"}, {"type": "null"}]},
            "mcp_rpm_limit": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}},
            "nullable_option": {"type": "string", "nullable": True},
            "model_max_budget": {"type": "object", "additionalProperties": {"$ref": "#/components/schemas/Budget"}},
            "max_budget": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        }
    )
    data["components"] = {
        "schemas": {
            "Permission": {
                "type": "object",
                "properties": {
                    "mcp_servers": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]},
                    "mcp_tool_permissions": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
                    "api_key": {"type": "string"},
                },
            },
            "Budget": {
                "type": "object",
                "properties": {"budget_limit": {"type": "number"}, "time_period": {"type": "string"}},
                "required": ["budget_limit", "time_period"],
            },
        }
    }
    return data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values,valid",
    [
        ({"object_permission": {"mcp_servers": ["server-1"], "mcp_tool_permissions": {"server-1": ["search"]}}}, True),
        ({"object_permission": None, "nullable_option": None}, True),
        ({"mcp_rpm_limit": {"server-1": 3}}, True),
        ({"object_permission": {"mcp_servers": "server-1"}}, False),
        ({"object_permission": {"api_key": "hidden-input"}}, False),
        ({"mcp_rpm_limit": {"server-1": "hidden-input"}}, False),
        ({"model_max_budget": {"model-a": {"budget_limit": 2, "time_period": "1d"}}}, True),
        ({"model_max_budget": {"model-a": {"budget_limit": 0, "time_period": "1d"}}}, False),
        ({"model_max_budget": {"model-a": {"budget_limit": 2, "time_period": "0d"}}}, False),
        ({"model_max_budget": {" model-a": {"budget_limit": 2, "time_period": "1d"}}}, False),
        ({"max_budget": -1}, False),
        ({"team_id": "hidden-input"}, False),
        ({"unadvertised": "hidden-input"}, False),
    ],
)
async def test_nested_mcp_model_budgets_and_static_limits(values, valid, monkeypatch):
    monkeypatch.setattr(policy_schemas.settings, "litellm_enterprise_enabled", True)
    discovery = {"available": True, "schemas": policy_schemas.extract_schemas(nested_document())}
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value=discovery)):
        payload = KeySettingsUpdate(advanced_settings=values)
        if valid:
            assert await policy_schemas.merge_settings("key_update", payload) == values
        else:
            with pytest.raises(HTTPException) as exc:
                await policy_schemas.merge_settings("key_update", payload)
            assert exc.value.status_code == 422
            assert "hidden-input" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_duplicates_rejected_but_legacy_updates_do_not_require_discovery():
    discovery = {"available": True, "schemas": policy_schemas.extract_schemas(nested_document())}
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value=discovery)) as fetch:
        assert await policy_schemas.merge_settings("key_update", KeySettingsUpdate(max_budget=10)) == {"max_budget": 10}
        fetch.assert_not_awaited()
        with pytest.raises(HTTPException) as exc:
            await policy_schemas.merge_settings("key_update", KeySettingsUpdate(max_budget=10, advanced_settings={"max_budget": 20}))
        assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_offline_advanced_writes_fail_closed():
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value={"available": False, "schemas": {}})):
        with pytest.raises(HTTPException) as exc:
            await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"new_policy": 1}))
        assert exc.value.status_code == 503


@pytest.mark.parametrize("ref", ["https://example.invalid/schema", "file:///etc/passwd", "#/components/schemas/Loop"])
def test_external_and_cyclic_refs_fail_without_resolution(ref):
    data = document({"policy": {"$ref": ref}})
    data["components"] = {"schemas": {"Loop": {"$ref": ref}}}
    with pytest.raises(ValueError):
        policy_schemas.extract_schemas(data)


def test_deep_schema_is_bounded():
    value = {"type": "string"}
    for _ in range(40):
        value = {"type": "array", "items": value}
    with pytest.raises(ValueError):
        policy_schemas.extract_schemas(document({"policy": value}))


@pytest.mark.asyncio
async def test_opaque_map_cannot_smuggle_credentials():
    schemas = policy_schemas.extract_schemas(document({"new_policy": {"type": "object", "additionalProperties": True}}))
    with (
        patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value={"available": True, "schemas": schemas})),
        pytest.raises(HTTPException) as exc,
    ):
        await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"new_policy": {"api_key": "hidden-input"}}))
    assert exc.value.status_code == 422
    assert "hidden-input" not in str(exc.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["team_create", "team_update"])
@pytest.mark.parametrize(
    "budget,enterprise,status",
    [
        ({"m": {"budget_limit": 1, "time_period": "1d"}}, False, 403),
        ({"m": {"budget_limit": 0, "time_period": "1d"}}, True, 422),
        ({"m": {"budget_limit": 1, "time_period": "0d"}}, True, 422),
    ],
)
async def test_future_team_permodel_schema_cannot_bypass_budget_validation(kind, budget, enterprise, status, monkeypatch):
    from app.models import TeamCreateRequest, TeamUpdateRequest

    monkeypatch.setattr(policy_schemas.settings, "litellm_enterprise_enabled", enterprise)
    payload_type = TeamCreateRequest if kind == "team_create" else TeamUpdateRequest
    kwargs = {"team_alias": "Team"} if kind == "team_create" else {}
    discovery = {"available": True, "schemas": policy_schemas.extract_schemas(nested_document())}
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value=discovery)):
        with pytest.raises(HTTPException) as exc:
            await policy_schemas.merge_settings(kind, payload_type(**kwargs, advanced_settings={"model_max_budget": budget}))
        assert exc.value.status_code == status
