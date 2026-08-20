from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models import CurrentUser, TeamCreateRequest, TeamUpdateRequest
from app.rate_limit import _key_ops
from app.routers.api_v1 import (
    ApiActor,
    api_create_team,
    api_delete_team,
    api_list_teams,
    api_update_team,
)


def setup_function():
    _key_ops.clear()


def admin_actor() -> ApiActor:
    return ApiActor(CurrentUser(user_id="admin", email="admin@example.com", role="admin"))


@pytest.mark.asyncio
async def test_normal_user_cannot_manage_teams():
    actor = ApiActor(CurrentUser(user_id="user", email="user@example.com"))
    with patch("app.routers.api_v1.llm.list_teams", new=AsyncMock()) as list_teams:
        with pytest.raises(HTTPException) as exc:
            await api_list_teams(1, 25, "", actor)
    assert exc.value.status_code == 403
    list_teams.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_team_list_includes_configuration_references(monkeypatch):
    from app.routers import api_v1

    monkeypatch.setattr(
        api_v1.settings,
        "oidc_group_team_mapping",
        {"Engineering": "team-eng", "Platform": ["team-eng", "team-shared"]},
    )
    monkeypatch.setattr(api_v1.settings, "key_team_id", "team-shared")
    page = {
        "teams": [{"team_id": "team-eng", "team_alias": "Engineering"}],
        "total": 1,
        "page": 1,
        "page_size": 25,
        "total_pages": 1,
    }
    with patch("app.routers.api_v1.llm.list_teams", new=AsyncMock(return_value=page)):
        result = await api_list_teams(1, 25, "eng", admin_actor())

    assert result["teams"][0]["mapped_groups"] == ["Engineering", "Platform"]
    assert result["teams"][0]["default_key_team"] is False


@pytest.mark.asyncio
async def test_admin_can_create_team():
    payload = TeamCreateRequest(
        team_alias="Engineering",
        team_id="team-eng",
        models=["gpt-4o", "gpt-4o"],
        max_budget=100,
        budget_duration="30d",
    )
    with patch(
        "app.routers.api_v1.llm.create_team",
        new=AsyncMock(return_value={"team_id": "team-eng", "team_alias": "Engineering"}),
    ) as create:
        result = await api_create_team(payload, admin_actor())

    assert result["team_id"] == "team-eng"
    create.assert_awaited_once_with(
        {
            "team_alias": "Engineering",
            "team_id": "team-eng",
            "models": ["gpt-4o"],
            "max_budget": 100.0,
            "budget_duration": "30d",
            "blocked": False,
        }
    )


@pytest.mark.asyncio
async def test_team_update_preserves_explicit_null_and_empty_models():
    payload = TeamUpdateRequest(models=[], max_budget=None, blocked=True)
    with patch(
        "app.routers.api_v1.llm.update_team",
        new=AsyncMock(return_value={"team_id": "team-eng", "models": [], "blocked": True}),
    ) as update:
        await api_update_team("team-eng", payload, admin_actor())

    update.assert_awaited_once_with(
        "team-eng", {"models": [], "max_budget": None, "blocked": True}
    )


@pytest.mark.asyncio
async def test_cannot_delete_team_referenced_by_sso_mapping(monkeypatch):
    from app.routers import api_v1

    monkeypatch.setattr(api_v1.settings, "oidc_group_team_mapping", {"Engineering": "team-eng"})
    monkeypatch.setattr(api_v1.settings, "key_team_id", None)
    with patch("app.routers.api_v1.llm.delete_team", new=AsyncMock()) as delete:
        with pytest.raises(HTTPException) as exc:
            await api_delete_team("team-eng", admin_actor())

    assert exc.value.status_code == 409
    assert "Engineering" in str(exc.value.detail)
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_can_delete_unreferenced_team(monkeypatch):
    from app.routers import api_v1

    monkeypatch.setattr(api_v1.settings, "oidc_group_team_mapping", {})
    monkeypatch.setattr(api_v1.settings, "key_team_id", None)
    with patch("app.routers.api_v1.llm.delete_team", new=AsyncMock(return_value={})) as delete:
        result = await api_delete_team("team-old", admin_actor())

    assert result == {"deleted": True, "team_id": "team-old"}
    delete.assert_awaited_once_with("team-old")


@pytest.mark.asyncio
async def test_litellm_team_crud_payloads():
    response = MagicMock(status_code=200)
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"team_id": "team-eng"})

    with patch("httpx.AsyncClient") as client_class:
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        client.post = AsyncMock(return_value=response)
        client_class.return_value.__aenter__ = AsyncMock(return_value=client)
        client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services import litellm

        response.json.return_value = {
            "teams": [{"team_id": "team-eng"}],
            "total": 1,
            "page": 2,
            "page_size": 10,
            "total_pages": 3,
        }
        page = await litellm.list_teams(page=2, page_size=10, search="eng")
        assert page["total"] == 1
        assert client.get.await_args.args[0].endswith("/v2/team/list")
        assert client.get.await_args.kwargs["params"]["search"] == "eng"

        response.json.return_value = {"team_id": "team-eng"}
        await litellm.create_team({"team_alias": "Engineering"})
        assert client.post.await_args.args[0].endswith("/team/new")
        assert client.post.await_args.kwargs["json"] == {"team_alias": "Engineering"}

        await litellm.update_team("team-eng", {"max_budget": 10})
        assert client.post.await_args.args[0].endswith("/team/update")
        assert client.post.await_args.kwargs["json"] == {"team_id": "team-eng", "max_budget": 10}

        await litellm.delete_team("team-eng")
        assert client.post.await_args.args[0].endswith("/team/delete")
        assert client.post.await_args.kwargs["json"] == {"team_ids": ["team-eng"]}
