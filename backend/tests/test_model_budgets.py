from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings, settings
from app.main import app
from app.models import BulkKeyUpdateRequest, CurrentUser, KeySettingsUpdate
from app.rate_limit import _key_ops
from app.routers.api_v1 import ApiActor, bulk_update_keys
from app.services import organization_sync


BUDGETS = {"claude-opus": {"budget_limit": 25, "time_period": "2h"}}


@pytest.mark.parametrize("enabled", [False, True])
async def test_rotation_cannot_drop_model_budgets_or_reset_model_windows(monkeypatch, enabled):
    monkeypatch.setattr(settings, "litellm_enterprise_enabled", enabled)
    key = {"token": "key-1", "user_id": "user", "key_alias": "old", "spend": 5, "model_max_budget": BUDGETS}
    with (
        patch("app.services.organization_sync.key_spend.current_keys", new=AsyncMock(return_value=[key])),
        patch("app.services.organization_sync._generate_key", new=AsyncMock(side_effect=AssertionError("Must not create a replacement"))) as generate,
        patch("app.services.organization_sync.litellm.update_key", new=AsyncMock()) as update,
        patch("app.services.organization_sync.litellm.delete_key", new=AsyncMock()) as delete,
    ):
        with pytest.raises(HTTPException) as exc:
            await organization_sync.rotate_key("user", "u@example.com", None, key_alias="old")
    assert exc.value.status_code == 409
    assert "per-model budgets" in exc.value.detail
    generate.assert_not_awaited()
    update.assert_not_awaited()
    delete.assert_not_awaited()


def test_enterprise_flag_defaults_off_and_reads_environment(monkeypatch, tmp_path):
    import app.config as config

    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path / "backend")
    monkeypatch.delenv("LITELLM_ENTERPRISE_ENABLED", raising=False)
    assert Settings().litellm_enterprise_enabled is False
    monkeypatch.setenv("LITELLM_ENTERPRISE_ENABLED", "true")
    assert Settings().litellm_enterprise_enabled is True


@pytest.mark.parametrize("enabled", [False, True])
async def test_portal_exposes_enterprise_flag(monkeypatch, enabled):
    monkeypatch.setattr(settings, "litellm_enterprise_enabled", enabled)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/portal-config")
    assert response.status_code == 200
    assert response.json()["litellm_enterprise_enabled"] is enabled


def test_model_budgets_survive_validation_without_changing_overall_budget():
    result = KeySettingsUpdate(model_max_budget=BUDGETS).model_dump(exclude_unset=True)
    assert result == {"model_max_budget": BUDGETS}
    assert KeySettingsUpdate(model_max_budget={}).model_dump(exclude_unset=True) == {"model_max_budget": {}}


@pytest.mark.parametrize(
    "budgets",
    [
        None,
        {"": {"budget_limit": 25, "time_period": "2h"}},
        {" opus ": {"budget_limit": 25, "time_period": "2h"}},
        {"opus": {"budget_limit": 0, "time_period": "2h"}},
        {"opus": {"budget_limit": -1, "time_period": "2h"}},
        {"opus": {"budget_limit": float("inf"), "time_period": "2h"}},
        {"opus": {"budget_limit": float("nan"), "time_period": "2h"}},
        {"opus": {"budget_limit": 25, "time_period": "0h"}},
        {"opus": {"budget_limit": 25, "time_period": "2"}},
        {"opus": {"budget_limit": 25, "time_period": "-2h"}},
        {"opus": {"budget_limit": 25, "time_period": "2hours"}},
        {"opus": {"budget_limit": 25}},
        {str(index): {"budget_limit": 25, "time_period": "2h"} for index in range(101)},
    ],
)
def test_invalid_model_budgets_are_rejected(budgets):
    with pytest.raises(ValidationError):
        KeySettingsUpdate(model_max_budget=budgets)


async def test_zero_model_budget_is_rejected_at_http_boundary(monkeypatch):
    monkeypatch.setattr(settings, "litellm_enterprise_enabled", True)
    monkeypatch.setattr(settings, "management_api_key", "synthetic-test-management")
    _key_ops.clear()
    with patch("app.routers.api_v1.key_budgets.update_key", new=AsyncMock()) as update:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.patch(
                "/api/v1/keys/bulk",
                headers={"X-API-Key": "synthetic-test-management"},
                json={"keys": ["key-1"], "settings": {"model_max_budget": {"opus": {"budget_limit": 0, "time_period": "2h"}}}},
            )
    assert response.status_code == 422
    assert any(error["loc"][-1] == "budget_limit" for error in response.json()["detail"])
    update.assert_not_awaited()


@pytest.mark.parametrize("budgets", [BUDGETS, {}])
async def test_disabled_enterprise_flag_rejects_model_budget_writes(monkeypatch, budgets):
    monkeypatch.setattr(settings, "litellm_enterprise_enabled", False)
    _key_ops.clear()
    actor = ApiActor(CurrentUser(user_id="admin", email="a@example.com", role="admin"))
    payload = BulkKeyUpdateRequest(keys=["key-1"], settings={"model_max_budget": budgets, "rpm_limit": 10})
    with patch("app.routers.api_v1.key_budgets.update_key", new=AsyncMock()) as update:
        with pytest.raises(HTTPException) as exc:
            await bulk_update_keys(payload, actor)
    assert exc.value.status_code == 403
    assert "LITELLM_ENTERPRISE_ENABLED" in exc.value.detail
    update.assert_not_awaited()


async def test_enabled_model_budgets_forward_to_litellm_with_partial_failures(monkeypatch):
    monkeypatch.setattr(settings, "litellm_enterprise_enabled", True)
    _key_ops.clear()
    actor = ApiActor(CurrentUser(user_id="admin", email="a@example.com", role="admin"))
    payload = BulkKeyUpdateRequest(keys=["key-1", "key-2"], settings={"model_max_budget": BUDGETS})
    with (
        patch("app.routers.api_v1.organization_sync.guard_key", new=AsyncMock()),
        patch("app.routers.api_v1.key_budgets.update_key", new=AsyncMock(side_effect=[{}, HTTPException(502, "License required")])) as update,
        patch("app.routers.api_v1._record_audit", new=AsyncMock()) as audit,
    ):
        result = await bulk_update_keys(payload, actor)
    assert result["updated"] == 1
    assert result["results"][1] == {"key": "key-2", "updated": False, "error": "License required"}
    update.assert_any_await("key-1", {"model_max_budget": BUDGETS}, use_key_budget_only=False)
    assert audit.await_args.kwargs["details"]["setting_fields"] == ["model_max_budget"]


@pytest.mark.parametrize("auth_source", ["sso", "litellm_key"])
async def test_model_budgets_remain_admin_only(monkeypatch, auth_source):
    monkeypatch.setattr(settings, "litellm_enterprise_enabled", True)
    actor = ApiActor(CurrentUser(user_id="user", email="u@example.com", auth_source=auth_source))
    with pytest.raises(HTTPException) as exc:
        await bulk_update_keys(BulkKeyUpdateRequest(keys=["key-1"], settings={"model_max_budget": BUDGETS}), actor)
    assert exc.value.status_code == 403
