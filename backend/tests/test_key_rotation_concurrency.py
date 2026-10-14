"""Concurrent portal rotations cannot multiply an owner's individual allowance."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.dependencies import get_current_user
from app.main import app
from app.models import CurrentUser
from app.rate_limit import _key_ops
from app.services import litellm, organization_client as upstream, organization_key_policy as policy, organization_sync as sync


@pytest.mark.asyncio
async def test_concurrent_http_rotations_leave_one_replacement_and_preserve_spend(monkeypatch):
    owner = CurrentUser(user_id="rotation-owner", email="owner@example.com")
    active = {"old": {"token": "old", "spend": 42.0}}
    counter = 0
    node = SimpleNamespace(team_id="leaf-team", per_user=100, duration="30d")

    async def list_keys(user_id):
        snapshot = [dict(item) for item in active.values()]
        await asyncio.sleep(0.01)
        return snapshot

    async def generate(user_id, email, team_id, **options):
        nonlocal counter
        counter += 1
        secret = f"synthetic-replacement-{counter}"
        active[secret] = {"token": secret, "spend": options["initial_spend"], "max_budget": options["max_budget"]}
        await asyncio.sleep(0.01)
        return {"key": secret, "user_id": user_id}

    async def delete(token):
        active.pop(token, None)

    _key_ops.clear()
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: owner)
    monkeypatch.setattr(litellm, "list_user_keys", list_keys)
    monkeypatch.setattr(litellm, "delete_key", delete)
    monkeypatch.setattr(sync, "prepare_user", AsyncMock(return_value=node))
    monkeypatch.setattr(upstream, "generate_key", generate)
    monkeypatch.setattr(policy, "normalize_individual_caps", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        results = await asyncio.wait_for(asyncio.gather(client.post("/api/keys/regenerate"), client.post("/api/keys/regenerate")), timeout=5)
    assert [result.status_code for result in results] == [201, 201]
    assert len(active) == 1
    assert next(iter(active.values()))["spend"] == 42.0
    assert sum(item["max_budget"] for item in active.values()) == 100
    _key_ops.clear()
