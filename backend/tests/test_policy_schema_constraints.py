import pytest
from jsonschema import Draft202012Validator

from app.services.policy_schemas_normalize import extract_schemas
from tests.test_policy_schemas import document


@pytest.mark.parametrize(
    "schema,valid,invalid",
    [
        ({"type": "object", "required": ["first"]}, {"first": 1}, {}),
        ({"type": "array", "prefixItems": [{"type": "string"}], "items": False}, ["ok"], [1]),
        ({"type": "array", "contains": {"type": "integer"}, "minContains": 1}, [1], ["bad"]),
        (
            {"type": "object", "patternProperties": {"^model-": {"type": "integer"}}, "additionalProperties": False},
            {"model-a": 1},
            {"model-a": "bad"},
        ),
        ({"type": "object", "dependentRequired": {"first": ["second"]}}, {"first": 1, "second": 2}, {"first": 1}),
        ({"if": {"type": "string"}, "then": {"minLength": 2}, "else": {"type": "integer", "minimum": 1}}, "ok", "x"),
    ],
)
def test_dynamic_schema_constraints_are_not_silently_dropped(schema, valid, invalid):
    normalized = extract_schemas(document({"future_field": schema}))["key_update"]["properties"]["future_field"]
    validator = Draft202012Validator(normalized)
    assert validator.is_valid(valid)
    assert not validator.is_valid(invalid)


def test_unknown_validation_keywords_fail_closed_without_hiding_supported_fields():
    normalized = extract_schemas(document({"unsupported": {"futureConstraint": True}, "supported": {"type": "number"}}))
    assert "unsupported" not in normalized["key_update"]["properties"]
    assert normalized["key_update"]["properties"]["supported"] == {"type": "number"}
