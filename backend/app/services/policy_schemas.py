"""Discover and validate administrator policy fields from configured LiteLLM."""

import asyncio
import copy
import json
import time
from itertools import islice

import httpx
from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker, SchemaError
from pydantic import ValidationError

from app.config import settings
from app.models import KeySettingsUpdate, TeamCreateRequest, TeamUpdateRequest
from app.services.litellm_client import client, headers
from app.services.policy_schemas_normalize import extract_schemas, forbidden

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
_cache: tuple[str, float, dict] | None = None
_lock = asyncio.Lock()
UNAVAILABLE = {"available": False, "schemas": {}, "detail": "LiteLLM policy schema is unavailable; advanced settings cannot be saved"}

CONSTRAINT_MESSAGES = {
    "type": "Must match the required type.",
    "required": "A required property is missing.",
    "minimum": "Must meet the minimum value.",
    "maximum": "Must not exceed the maximum value.",
    "exclusiveMinimum": "Must exceed the minimum value.",
    "exclusiveMaximum": "Must be below the maximum value.",
    "multipleOf": "Must be a multiple of the required increment.",
    "enum": "Choose one of the allowed values.",
    "const": "Must match the required constant.",
    "minLength": "Text is shorter than the allowed minimum.",
    "maxLength": "Text is longer than the allowed maximum.",
    "pattern": "Text does not match the required pattern.",
    "format": "Must match the required format.",
    "minItems": "Too few items.",
    "maxItems": "Too many items.",
    "uniqueItems": "Items must be unique.",
    "additionalProperties": "Contains an unsupported property.",
    "minProperties": "Too few properties.",
    "maxProperties": "Too many properties.",
}


def _safe_path(schema: dict, path) -> list:
    """Only echo schema-defined names and array indexes, never submitted map keys."""
    result = []
    for part in list(path)[:32]:
        variants = [schema]
        for item in variants:
            for union in ("anyOf", "oneOf", "allOf"):
                variants.extend(value for value in item.get(union, []) if isinstance(value, dict))
        if type(part) is int:
            result.append(part)
            candidates = []
            for item in variants:
                prefix = item.get("prefixItems", [])
                candidates.append(prefix[part] if 0 <= part < len(prefix) else item.get("items", {}))
        else:
            properties = {name: value for item in variants for name, value in item.get("properties", {}).items()}
            result.append(part if part in properties else "<property>")
            candidates = [properties.get(part, {})]
        schema = {"anyOf": [value for value in candidates if isinstance(value, dict)]}
    return result


def _nested_errors(error):
    """Keep precise branch failures for nullable/union schemas, omitting root type noise."""
    if not error.context:
        return [error]
    leaves = [leaf for child in error.context for leaf in _nested_errors(child)][:20]
    depth = max(len(leaf.absolute_path) for leaf in leaves)
    return [leaf for leaf in leaves if len(leaf.absolute_path) == depth]


def _policy_errors(exc: ValidationError, properties: dict) -> list[dict]:
    return [
        {
            "loc": ["body", "advanced_settings", *_safe_path({"properties": properties}, error["loc"])],
            "msg": "Must satisfy LiteGate policy limits.",
            "type": "policy.validation",
        }
        for error in exc.errors(include_input=False, include_context=False, include_url=False)[:20]
    ]


async def _fetch_schemas() -> dict:
    async with (
        client() as upstream,
        upstream.stream("GET", f"{settings.litellm_url.rstrip('/')}/openapi.json", headers=headers(), timeout=10, follow_redirects=False) as response,
    ):
        response.raise_for_status()
        chunks = bytearray()
        async for chunk in response.aiter_bytes():
            chunks.extend(chunk)
            if len(chunks) > MAX_DOCUMENT_BYTES:
                raise ValueError("Schema document too large")
    document = json.loads(chunks)
    return {"available": True, "schemas": extract_schemas(document)}


async def get_policy_schemas() -> dict:
    global _cache
    source = settings.litellm_url
    if _cache is not None and _cache[0] == source and time.monotonic() < _cache[1]:
        return copy.deepcopy(_cache[2])
    async with _lock:
        if _cache is not None and _cache[0] == source and time.monotonic() < _cache[1]:
            return copy.deepcopy(_cache[2])
        try:
            result = await _fetch_schemas()
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, RecursionError, SchemaError):
            result = UNAVAILABLE
        _cache = (source, time.monotonic() + (300 if result["available"] else 30), result)
        return copy.deepcopy(result)


def _safe_values(value, depth=0) -> bool:
    if depth > 32:
        return False
    if isinstance(value, dict):
        return all(not forbidden(name) and _safe_values(item, depth + 1) for name, item in value.items())
    if isinstance(value, list):
        return all(_safe_values(item, depth + 1) for item in value)
    return True


async def merge_settings(kind: str, payload) -> dict:
    if payload is None:
        return {}
    changes = payload.model_dump(exclude_unset=kind != "team_create", exclude_none=kind == "team_create")
    advanced = changes.pop("advanced_settings", None)
    if not advanced:
        return changes
    try:
        if len(json.dumps(advanced, allow_nan=False)) > 65536:
            raise ValueError("Too large")
    except (ValueError, RecursionError):
        raise HTTPException(status_code=422, detail="Advanced settings exceed safe JSON limits") from None
    if not _safe_values(advanced):
        raise HTTPException(status_code=422, detail="Advanced settings contain protected fields or excessive nesting")
    discovery = await get_policy_schemas()
    if not discovery["available"]:
        raise HTTPException(status_code=503, detail=UNAVAILABLE["detail"])
    properties = discovery["schemas"][kind]["properties"]
    if any(name not in properties or forbidden(name) or name in payload.model_fields_set - {"advanced_settings"} for name in advanced):
        raise HTTPException(status_code=422, detail="Advanced settings contain unknown, protected, or duplicate fields")
    errors = []
    for name, value in advanced.items():
        validator = Draft202012Validator(properties[name], format_checker=FormatChecker())
        failures = (leaf for error in validator.iter_errors(value) for leaf in _nested_errors(error))
        for error in islice(failures, 20 - len(errors)):
            errors.append(
                {
                    "loc": ["body", "advanced_settings", name, *_safe_path(properties[name], error.absolute_path)],
                    "msg": CONSTRAINT_MESSAGES.get(error.validator, "Must satisfy the advertised schema constraint."),
                    "type": f"schema.{error.validator}",
                }
            )
        if len(errors) == 20:
            break
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    if "model_max_budget" in advanced:
        try:
            advanced = {
                **advanced,
                "model_max_budget": KeySettingsUpdate.model_validate({"model_max_budget": advanced["model_max_budget"]}).model_dump()[
                    "model_max_budget"
                ],
            }
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_policy_errors(exc, properties)) from None
        if not settings.litellm_enterprise_enabled:
            raise HTTPException(status_code=403, detail="Per-model budgets require LITELLM_ENTERPRISE_ENABLED=true and a LiteLLM Enterprise license")
    # Known fields retain LiteGate's stricter normalization and validation, including
    # positive per-model budget caps. Never include validation inputs in errors.
    model = {"key_update": KeySettingsUpdate, "team_create": TeamCreateRequest, "team_update": TeamUpdateRequest}[kind]
    known = {name: value for name, value in advanced.items() if name in model.model_fields and name != "advanced_settings"}
    if known:
        try:
            normalized = model.model_validate({**changes, **known}).model_dump(include=set(known))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_policy_errors(exc, properties)) from None
        advanced = {**advanced, **normalized}
    return {**changes, **advanced}
