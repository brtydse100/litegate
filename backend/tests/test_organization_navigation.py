"""Progressive organization metadata and selected-team reporting contracts."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import organization_client as upstream, organization_reports as reports
from tests.test_organization_reports import setup


@pytest.mark.asyncio
async def test_children_only_direct_metadata_without_upstream_reads(monkeypatch, setup):
    fetch = AsyncMock()
    monkeypatch.setattr(upstream, "team_info", fetch)
    roots = await reports.children(None)
    assert roots["groups"]
    assert all(group["parent_id"] is None for group in roots["groups"])
    assert all("group_spend" not in group for group in roots["groups"])
    for root in roots["groups"]:
        children = await reports.children(root["id"])
        assert all(group["parent_id"] == root["id"] for group in children["groups"])
        assert root["has_children"] == bool(children["groups"])
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_detail_reads_only_selected_team_and_labels_own_spend(monkeypatch, setup):
    node = setup.resolve("alice", ["squad1"])
    fetch = AsyncMock(return_value={"team_info": {"spend": 7, "max_budget": None, "budget_duration": node.duration}})
    monkeypatch.setattr(upstream, "team_info", fetch)
    result = await reports.group_detail(node.id)
    fetch.assert_awaited_once_with(node.team_id)
    assert result["group_spend"] == 7
    assert result["spend_scope"] == "team"
    assert result["members"] == 1
    assert result["sync_error"] is None


@pytest.mark.asyncio
async def test_unknown_lazy_groups_reject_before_upstream_reads(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(upstream, "team_info", fetch)
    for operation in (reports.children, reports.group_detail):
        with pytest.raises(HTTPException) as exc:
            await operation("missing")
        assert exc.value.status_code == 404
    fetch.assert_not_awaited()
