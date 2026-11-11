from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import organization_store, organization_sync, litellm
from tests.test_organization_config import example


@pytest.mark.parametrize("field", ["budget_limits", "temp_budget_increase", "new_budget_override", "team_member_budget"])
async def test_discovered_allowance_fields_cannot_override_managed_key(monkeypatch, field):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    team_id = next(iter(tree.nodes.values())).team_id
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "user", "team_id": team_id}))
    monkeypatch.setattr(organization_store, "get", lambda _: None)
    with pytest.raises(HTTPException) as exc:
        await organization_sync.guard_key("key", {field: 1000})
    assert exc.value.status_code == 409


@pytest.mark.parametrize("field", ["budget_limits", "team_member_budget", "new_budget_override"])
def test_discovered_allowance_fields_cannot_override_managed_team(monkeypatch, field):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    with pytest.raises(HTTPException) as exc:
        organization_sync.guard_team(next(iter(tree.nodes.values())).team_id, {field: 1000})
    assert exc.value.status_code == 409


async def test_separate_model_caps_and_mcp_permissions_do_not_change_inherited_allowance(monkeypatch):
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(example()))
    lookup = AsyncMock()
    monkeypatch.setattr(litellm, "get_key_info", lookup)
    await organization_sync.guard_key(
        "key", {"model_max_budget": {"opus": {"budget_limit": 25, "time_period": "2h"}}, "object_permission": {"mcp_servers": []}}
    )
    lookup.assert_not_awaited()
