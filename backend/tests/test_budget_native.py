"""Native aggregate member updates never multiply an allowance across keys."""

from importlib import import_module, util
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


def native():
    assert util.find_spec("app.services.budget_native") is not None, "Native budget verification is required"
    return import_module("app.services.budget_native")


@pytest.mark.asyncio
async def test_unknown_runtime_and_newer_version_never_enable_unverified_enforcement(monkeypatch):
    adapter = native()
    monkeypatch.setattr(adapter.upstream, "request", AsyncMock(return_value={"version": "1.109.1"}))
    capability = await adapter.capabilities()
    assert capability["supported"] is False
    assert capability["version"] == "1.109.1"
    assert any("reservation" in reason for reason in capability["reasons"])
    with pytest.raises(HTTPException) as failed:
        await adapter.require_capability()
    assert failed.value.status_code == 503


@pytest.mark.asyncio
async def test_decreases_verify_before_any_increase_and_retry_preserves_pending(monkeypatch):
    adapter = native()
    from app.services import budget_store

    targets = [{"team_id": "t", "user_id": "alice", "amount": 5_000_000}, {"team_id": "t", "user_id": "bob", "amount": 15_000_000}]
    budget_store.queue(0, targets)
    values = {"alice": 10_000_000, "bob": 10_000_000}
    events = []

    async def read(target):
        events.append(("read", target["user_id"]))
        return values[target["user_id"]]

    async def write(target):
        events.append(("write", target["user_id"]))
        if target["user_id"] == "alice":
            raise HTTPException(502, "secret upstream diagnostic")
        values[target["user_id"]] = target["amount"]

    monkeypatch.setattr(adapter, "read_amount", read)
    monkeypatch.setattr(adapter, "write_amount", write)
    assert await adapter.apply_pending(0) is False
    assert ("write", "bob") not in events
    assert len(budget_store.pending(0)) == 2

    async def working_write(target):
        events.append(("write", target["user_id"]))
        values[target["user_id"]] = target["amount"]

    events.clear()
    monkeypatch.setattr(adapter, "write_amount", working_write)
    assert await adapter.apply_pending(0) is True
    assert events.index(("write", "alice")) < events.index(("write", "bob"))
    assert events[events.index(("write", "alice")) + 1] == ("read", "alice")
    assert budget_store.pending(0) == []


@pytest.mark.asyncio
async def test_multiple_keys_share_one_native_member_cap_without_resetting_spend(monkeypatch):
    adapter = native()
    request = AsyncMock(return_value={})
    monkeypatch.setattr(adapter.upstream, "request", request)
    await adapter.write_amount({"team_id": "team", "user_id": "alice", "amount": 12_000_000})
    assert request.call_args.args == ("POST", "/team/member_update")
    assert request.call_args.kwargs["payload"] == {"team_id": "team", "user_id": "alice", "max_budget_in_team": 12.0}


@pytest.mark.asyncio
async def test_readback_mismatch_keeps_policy_pending(monkeypatch):
    adapter = native()
    from app.services import budget_store

    budget_store.queue(0, [{"team_id": "t", "amount": 5}])
    monkeypatch.setattr(adapter, "read_amount", AsyncMock(return_value=10))
    monkeypatch.setattr(adapter, "write_amount", AsyncMock())
    assert await adapter.apply_pending(0) is False
    assert len(budget_store.pending(0)) == 1
