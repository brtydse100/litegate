from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models import KeySettingsUpdate
from app.services import policy_schemas
from tests.test_policy_schemas import document


@pytest.mark.asyncio
async def test_nested_error_identifies_schema_path_without_echoing_value():
    fields = {"limits": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "integer"}}}}}
    schemas = policy_schemas.extract_schemas(document(fields))
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value={"available": True, "schemas": schemas})):
        with pytest.raises(HTTPException) as failure:
            await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"limits": {"items": ["hidden-credential"]}}))
    assert failure.value.detail == [
        {"loc": ["body", "advanced_settings", "limits", "items", 0], "msg": "Must match the required type.", "type": "schema.type"}
    ]
    assert "hidden-credential" not in str(failure.value.detail)


@pytest.mark.asyncio
async def test_map_property_keys_are_not_echoed_and_errors_are_bounded():
    fields = {"limits": {"type": "object", "additionalProperties": {"type": "integer"}}}
    schemas = policy_schemas.extract_schemas(document(fields))
    values = {f"hidden-{i}": "hidden-value" for i in range(50)}
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value={"available": True, "schemas": schemas})):
        with pytest.raises(HTTPException) as failure:
            await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"limits": values}))
    assert isinstance(failure.value.detail, list)
    assert 1 <= len(failure.value.detail) <= 20
    assert "hidden-" not in str(failure.value.detail)


@pytest.mark.asyncio
async def test_nullable_object_failure_identifies_nested_item_not_only_union():
    fields = {"limits": {"anyOf": [{"type": "null"}, {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "integer"}}}}]}}
    schemas = policy_schemas.extract_schemas(document(fields))
    with patch.object(policy_schemas, "get_policy_schemas", AsyncMock(return_value={"available": True, "schemas": schemas})):
        with pytest.raises(HTTPException) as failure:
            await policy_schemas.merge_settings("key_update", KeySettingsUpdate(advanced_settings={"limits": {"items": ["hidden-credential"]}}))
    assert failure.value.detail[0]["loc"] == ["body", "advanced_settings", "limits", "items", 0]
    assert failure.value.detail[0]["type"] == "schema.type"
