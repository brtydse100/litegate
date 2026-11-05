import json
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import HTTPException
from app.config import settings
from app.services import litellm, litellm_client, organization_sync as sync


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["ignored_seed", "policy_reset", "stale_listing", None])
@pytest.mark.parametrize("move_first", [True, False])
async def test_transport_rotation_preserves_verified_spend_or_keeps_original(monkeypatch, fault, move_first):
    records = {"old": {"token": "old", "user_id": "owner", "key_alias": "owner key", "spend": 0.04, "team_id": "a"}}
    sequence = -1

    def handle(request):
        nonlocal sequence
        path = request.url.path
        data = json.loads(request.content) if request.content else {}
        if path == "/user/info":
            keys = [dict(row) for row in records.values()]
            if fault == "stale_listing":
                for row in keys:
                    row["spend"] = 0
            return httpx.Response(200, json={"keys": keys})
        if path == "/key/list":
            return httpx.Response(200, json={"keys": list(records.values()), "total_count": len(records), "total_pages": 1})
        if path == "/key/bulk_update":
            for changes in data["keys"]:
                records[changes.pop("key")].update(changes)
            return httpx.Response(200, json={"failed_updates": []})
        if path == "/key/info":
            return httpx.Response(200, json={"info": records[request.url.params["key"]]})
        if path == "/key/update":
            records[data.pop("key")].update(data)
            return httpx.Response(200, json={})
        if path == "/key/generate":
            sequence += 1
            key = "old" if sequence == 0 else f"new-{sequence}"
            records[key] = {**data, "token": key, "spend": 0 if fault == "ignored_seed" else data.get("spend", 0)}
            return httpx.Response(200, json={"key": key})
        if path == "/key/delete":
            for key in data["keys"]:
                del records[key]
            return httpx.Response(200, json={})
        raise AssertionError(path)

    async def preserve(*args):
        if fault == "policy_reset":
            records[args[-1]]["spend"] = 0

    monkeypatch.setattr(settings, "save_api_keys_in_db", False)
    monkeypatch.setattr(sync, "prepare_user", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.key_budgets.preserve_rotation_budget", preserve)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(litellm_client, "_shared_client", client)
        records.clear()
        created = await litellm.generate_key("owner", key_alias="owner key")
        assert created["key"] == "old"
        await litellm.update_key("old", {"spend": 0.04, "team_id": "a"})
        if move_first:
            await litellm.move_user_team_keys("owner", "a", "b")
        if fault in ("ignored_seed", "policy_reset"):
            for _ in range(2):
                with pytest.raises(HTTPException):
                    await sync.rotate_key("owner", "", None, key_alias="owner key")
                assert list(records) == ["old"]
                assert records["old"]["spend"] == 0.04
                assert records["old"]["key_alias"] == "owner key"
        else:
            for _ in range(3):
                result = await sync.rotate_key("owner", "", None, key_alias="owner key")
                if not move_first:
                    await litellm.move_user_team_keys("owner", "a", "b")
                assert len(records) == 1
                assert records[result["key"]]["spend"] == 0.04


@pytest.mark.asyncio
@pytest.mark.parametrize("spend", [None, "bad", -1, True])
async def test_invalid_live_source_is_not_treated_as_zero(monkeypatch, spend):
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "old", "spend": 0}]))
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "owner", "spend": spend}))
    generate = AsyncMock()
    monkeypatch.setattr(sync, "_generate_key", generate)
    with pytest.raises(HTTPException):
        await sync.rotate_key("owner", "", None, key_alias="owner key")
    generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("source,replacement,accepted", [(0, 0, True), (0, 0.04, False), (0.05, 0.04, False), (0.04, 0, False)])
async def test_final_verification_respects_period_reset_and_new_usage(monkeypatch, source, replacement, accepted):
    from app.services import key_spend

    async def info(key):
        return {"user_id": "owner", "spend": source if key == "old" else replacement, "budget_reset_at": "2026-12-01"}

    monkeypatch.setattr(litellm, "get_key_info", info)
    if accepted:
        await key_spend.verify_replacement("owner", [{"token": "old", "spend": 999, "budget_reset_at": "2026-11-01"}], "new")
    else:
        with pytest.raises(HTTPException):
            await key_spend.verify_replacement("owner", [{"token": "old", "spend": 999, "budget_reset_at": "2026-11-01"}], "new")


@pytest.mark.asyncio
async def test_live_key_reads_bound_concurrency_and_reject_foreign_owners(monkeypatch):
    import asyncio
    from app.services import key_spend

    active, peak = 0, 0

    async def info(key):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return {"user_id": "owner", "spend": 0.000001}

    monkeypatch.setattr(litellm, "get_key_info", info)
    result = await key_spend.current_keys("owner", [{"token": str(n), "spend": 0} for n in range(20)])
    assert peak == 5
    assert all(key["spend"] == 0.000001 for key in result)
    with pytest.raises(HTTPException):
        await key_spend.current_keys("other", [{"token": "old"}])


@pytest.mark.asyncio
async def test_homepage_api_uses_live_spend_over_stale_zero(monkeypatch):
    from app.models import CurrentUser
    from app.routers.keys import list_keys

    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "old", "spend": 0}]))
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "owner", "spend": 0.04}))
    monkeypatch.setattr(sync, "personal_policy", AsyncMock(return_value=None))
    result = await list_keys(CurrentUser(user_id="owner", email="owner@example.invalid"))
    assert result["keys"][0]["spend"] == 0.04


@pytest.mark.asyncio
async def test_ambiguous_source_counter_decrease_cannot_approve_zero_replacement(monkeypatch):
    from app.services import key_spend

    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "owner", "spend": 0}))
    with pytest.raises(HTTPException, match="decreased"):
        await key_spend.verify_replacement("owner", [{"token": "old", "spend": 0.04}], "new")


@pytest.mark.asyncio
@pytest.mark.parametrize("reset", [None, "", "invalid", "2026-11-01", "2026-12-01"])
async def test_source_decrease_requires_valid_advancing_reset_timestamp(monkeypatch, reset):
    from app.services import key_spend

    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "owner", "spend": 0, "budget_reset_at": reset}))
    with pytest.raises(HTTPException, match="decreased"):
        await key_spend.verify_replacement("owner", [{"token": "old", "spend": 0.04, "budget_reset_at": "2026-12-01"}], "new")
