from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models import CurrentUser, TeamUpdateRequest
from app.rate_limit import _key_ops
from app.routers import api_v1
from app.routers.api_actor import ApiActor


def prepare(monkeypatch, current):
    _key_ops.clear()
    monkeypatch.setattr(api_v1.policy_schemas, "merge_settings", AsyncMock(return_value={"mcp_rpm_limit": {"local": 7}}))
    monkeypatch.setattr(api_v1.organization_sync, "guard_team", lambda *_: None)
    monkeypatch.setattr(api_v1.policy_team_update.upstream, "team_info", AsyncMock(return_value={"team_info": current}))
    update = AsyncMock(return_value={"team_id": "team"})
    monkeypatch.setattr(api_v1.llm, "update_team", update)
    monkeypatch.setattr(api_v1, "_record_audit", AsyncMock())
    return update


async def test_advanced_team_mcp_update_preserves_metadata_and_member_allowance(monkeypatch):
    current = {
        "team_id": "team",
        "metadata": {"team_member_budget_id": "budget", "existing": "keep"},
        "team_member_budget_table": {"max_budget": 20, "budget_duration": "1h"},
    }
    update = prepare(monkeypatch, current)
    actor = ApiActor(CurrentUser(user_id="admin", email="admin@example.invalid", role="admin"))
    await api_v1.api_update_team("team", TeamUpdateRequest(advanced_settings={"mcp_rpm_limit": {"local": 7}}), actor)
    update.assert_awaited_once_with("team", {"mcp_rpm_limit": {"local": 7}, "metadata": current["metadata"], "team_member_budget": 20})
    assert current["metadata"]["team_member_budget_id"] == "budget"
    assert api_v1._record_audit.await_args.kwargs["details"]["setting_fields"] == ["mcp_rpm_limit"]


async def test_advanced_team_update_fails_before_mutation_when_member_policy_cannot_be_preserved(monkeypatch):
    update = prepare(monkeypatch, {"team_id": "team", "metadata": {"team_member_budget_id": "budget"}, "team_member_budget_table": None})
    actor = ApiActor(CurrentUser(user_id="admin", email="admin@example.invalid", role="admin"))
    with pytest.raises(HTTPException) as exc:
        await api_v1.api_update_team("team", TeamUpdateRequest(advanced_settings={"mcp_rpm_limit": {"local": 7}}), actor)
    assert exc.value.status_code == 503
    update.assert_not_awaited()
