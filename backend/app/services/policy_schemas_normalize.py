"""Bounded, local-reference-only normalization of upstream policy schemas."""

import re

from jsonschema import Draft202012Validator

PATHS = {"key_update": "/key/update", "team_create": "/team/new", "team_update": "/team/update"}
FORBIDDEN = {
    "key",
    "keys",
    "token",
    "api_key",
    "user_id",
    "team_id",
    "organization_id",
    "budget_id",
    "spend",
    "model_spend",
    "members",
    "members_with_roles",
    "team_memberships",
    "admins",
    "user_role",
    "auto_rotate",
    "rotation_interval",
    "agent_id",
    "router_settings",
    "permissions",
    "metadata",
    "config",
    "litellm_params",
    "aliases",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
}
SCALARS = {
    "required",
    "type",
    "title",
    "description",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
    "minContains",
    "maxContains",
    "dependentRequired",
}
SCHEMA_VALUES = {"items", "not", "contains", "propertyNames", "unevaluatedProperties", "unevaluatedItems", "if", "then", "else"}
SCHEMA_ARRAYS = {"anyOf", "oneOf", "allOf", "prefixItems"}
SCHEMA_MAPS = {"patternProperties", "dependentSchemas"}
ANNOTATIONS = {"default", "example", "examples", "deprecated", "discriminator", "xml", "externalDocs", "$schema", "$id", "$anchor", "$comment"}


def forbidden(name: str) -> bool:
    return name in FORBIDDEN or bool(
        re.search(r"secret|password|credential|authorization|access_token|refresh_token|api_key|private_key", name, re.IGNORECASE)
    )


def extract_schemas(document: dict) -> dict:
    remaining = [20000]

    def normalize(node, depth=0, seen=frozenset()):
        remaining[0] -= 1
        if depth > 32 or remaining[0] < 0:
            raise ValueError("Schema exceeds safe complexity")
        if isinstance(node, bool):
            return node
        if not isinstance(node, dict):
            raise TypeError("Invalid schema")
        if node.get("readOnly") or node.get("writeOnly") or node.get("format") in {"password", "binary"}:
            return False
        if "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/components/schemas/") or ref in seen:
                raise ValueError("Unsupported schema reference")
            target = document
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return normalize({**target, **{k: v for k, v in node.items() if k != "$ref"}}, depth + 1, seen | {ref})
        supported = (
            SCALARS
            | SCHEMA_VALUES
            | SCHEMA_ARRAYS
            | SCHEMA_MAPS
            | ANNOTATIONS
            | {"properties", "required", "additionalProperties", "nullable", "readOnly", "writeOnly"}
        )
        if any(key not in supported and not key.startswith("x-") for key in node):
            # Never advertise a field after silently weakening unknown constraints.
            return False
        result = {key: value for key, value in node.items() if key in SCALARS}
        if "properties" in node:
            properties = {}
            for name, value in node["properties"].items():
                if forbidden(name):
                    continue
                normalized = normalize(value, depth + 1, seen)
                if normalized is not False:
                    properties[name] = normalized
            result["properties"] = properties
            result["additionalProperties"] = False
            if "required" in node:
                result["required"] = [name for name in node["required"] if name in properties]
        elif "additionalProperties" in node:
            result["additionalProperties"] = normalize(node["additionalProperties"], depth + 1, seen)
        for key in SCHEMA_VALUES:
            if key in node:
                result[key] = normalize(node[key], depth + 1, seen)
        for key in SCHEMA_ARRAYS:
            if key in node:
                result[key] = [normalize(item, depth + 1, seen) for item in node[key]]
        for key in SCHEMA_MAPS:
            if key in node:
                result[key] = {name: normalize(value, depth + 1, seen) for name, value in node[key].items()}
        if node.get("nullable"):
            result = {"anyOf": [result, {"type": "null"}]}
        return result

    schemas = {}
    for name, path in PATHS.items():
        raw = document["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        schema = normalize(raw)
        if not isinstance(schema, dict) or "properties" not in schema:
            raise ValueError("Missing request properties")
        schema.pop("required", None)
        Draft202012Validator.check_schema(schema)
        schemas[name] = schema
    return schemas
