import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.services import litellm


@pytest.mark.asyncio
async def test_get_user_returns_none_on_404():
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import get_user
        result = await get_user("missing-user")
        assert result is None


@pytest.mark.asyncio
async def test_get_user_raises_503_on_transport_error():
    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import get_user
        with pytest.raises(HTTPException) as exc:
            await get_user("any-user")
        assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_user_raises_502_on_http_status_error():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock(status_code=401))
    )

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import get_user
        with pytest.raises(HTTPException) as exc:
            await get_user("any-user")
        assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_ensure_user_exists_returns_none_on_error():
    with patch("app.services.litellm.get_user", side_effect=HTTPException(status_code=503, detail="down")):
        from app.services.litellm import ensure_user_exists
        result = await ensure_user_exists("user-1", "user@example.com")
        assert result is None


@pytest.mark.asyncio
async def test_generate_key_sets_alias_from_email():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"key": "sk-abc", "user_id": "u1"})

    captured: dict = {}

    async def fake_post(url, json, headers, timeout):
        captured.update(json)
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.post = fake_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import generate_key
        await generate_key("user-1", "alice@example.com")

    assert captured.get("key_alias") == "alice's key"


@pytest.mark.asyncio
async def test_generate_key_sets_initial_spend_and_replacement_alias():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"key": "sk-abc"})
    captured: dict = {}

    async def fake_post(url, json, headers, timeout):
        captured.update(json)
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.post = fake_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
        await litellm.generate_key(
            "user-1",
            "alice@example.com",
            initial_spend=4.25,
            key_alias="rotation-1",
        )

    assert captured["spend"] == 4.25
    assert captured["key_alias"] == "rotation-1"


@pytest.mark.asyncio
async def test_generate_key_explicit_team_overrides_default(monkeypatch):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"key": "sk-abc"})
    captured: dict = {}

    async def fake_post(url, json, headers, timeout):
        captured.update(json)
        return mock_response

    monkeypatch.setattr(litellm.settings, "key_team_id", "team-default")
    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.post = fake_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        await litellm.generate_key("user-1", "alice@example.com", "team-sso")

    assert captured["team_id"] == "team-sso"


def test_total_key_spend_ignores_invalid_and_negative_values():
    keys = [
        {"spend": 1.25},
        {"spend": "2.5"},
        {"spend": -3},
        {"spend": "not-a-number"},
        {"spend": float("inf")},
    ]
    assert litellm.total_key_spend(keys) == 3.75


@pytest.mark.asyncio
async def test_list_user_team_ids_parses_and_deduplicates_response():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value=[
            {"team_id": "team-existing"},
            {"team_id": "team-existing"},
            {"team_id": "team-other"},
        ]
    )

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import list_user_team_ids
        result = await list_user_team_ids("user-1")

    assert result == ["team-existing", "team-other"]
    instance.get.assert_awaited_once()
    assert instance.get.await_args.kwargs["params"] == {"user_id": "user-1"}


@pytest.mark.asyncio
async def test_list_key_identifiers_reads_every_page_and_deduplicates():
    pages = [
        {
            "keys": [{"token": "key-1"}, {"api_key": "key-2"}],
            "total": 3,
            "total_pages": 2,
        },
        {
            "keys": [{"key": "key-2"}, {"key": "key-3"}],
            "total": 3,
            "total_pages": 2,
        },
    ]
    with patch("app.services.litellm.list_keys", new=AsyncMock(side_effect=pages)) as listing:
        result = await litellm.list_key_identifiers()

    assert result == ["key-1", "key-2", "key-3"]
    assert [call.kwargs for call in listing.await_args_list] == [
        {"page": 1, "size": 100},
        {"page": 2, "size": 100},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "page",
    [
        {"keys": [], "total": 5001, "total_pages": 1},
        {"keys": [], "total": 1, "total_pages": 51},
    ],
)
async def test_list_key_identifiers_stops_above_safety_limit(page):
    with patch("app.services.litellm.list_keys", new=AsyncMock(return_value=page)):
        with pytest.raises(HTTPException) as exc:
            await litellm.list_key_identifiers()

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_global_key_search_filters_before_paginating():
    keys = [
        {"token": "key-1", "key_alias": "Research", "user_email": "alice@example.com", "team_id": "team-a", "blocked": False},
        {"token": "key-2", "key_alias": "Production", "user_email": "bob@example.com", "team_id": "team-b", "blocked": True},
        {"token": "key-3", "key_alias": "Research backup", "user_email": "carol@example.com", "team_id": "team-a", "blocked": True},
    ]
    with patch("app.services.litellm.list_all_keys", new=AsyncMock(return_value=keys)):
        result = await litellm.list_keys_filtered(
            page=1,
            size=25,
            search="research",
            team_id="team-a",
            blocked=True,
        )

    assert result["total"] == 1
    assert [key["token"] for key in result["keys"]] == ["key-3"]


@pytest.mark.asyncio
async def test_filtered_identifier_selection_matches_search_scope():
    keys = [
        {"token": "key-1", "user_id": "alice", "team_id": "team-a"},
        {"token": "key-2", "user_id": "bob", "team_id": "team-b"},
    ]
    with patch("app.services.litellm.list_all_keys", new=AsyncMock(return_value=keys)):
        result = await litellm.list_key_identifiers(search="bob")

    assert result == ["key-2"]


@pytest.mark.asyncio
async def test_add_user_to_team_uses_member_add_payload():
    mock_response = MagicMock(status_code=200)
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"team_id": "team-1"})

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import add_user_to_team
        await add_user_to_team("user-1", "user@example.com", "team-1")

    assert instance.post.await_args.kwargs["json"] == {
        "team_id": "team-1",
        "member": {"role": "user", "user_id": "user-1"},
    }


@pytest.mark.asyncio
async def test_add_user_to_team_treats_only_duplicate_400_as_success():
    duplicate = MagicMock(status_code=400, text="")
    duplicate.json = MagicMock(return_value={"error_code": "team_member_already_in_team"})
    duplicate.raise_for_status = MagicMock(side_effect=AssertionError("must not raise"))

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=duplicate)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import add_user_to_team
        result = await add_user_to_team("user-1", "", "team-1")

    assert result == {"already_member": True, "team_id": "team-1"}


@pytest.mark.asyncio
async def test_add_user_to_team_rejects_other_400_errors():
    request = httpx.Request("POST", "http://litellm/team/member_add")
    response = httpx.Response(400, json={"detail": "team does not exist"}, request=request)

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import add_user_to_team
        with pytest.raises(HTTPException) as exc:
            await add_user_to_team("user-1", "user@example.com", "missing")

    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_sync_user_team_memberships_only_adds_missing_teams():
    with (
        patch(
            "app.services.litellm.list_user_team_ids",
            new=AsyncMock(return_value=["team-existing"]),
        ),
        patch("app.services.litellm.add_user_to_team", new=AsyncMock()) as add,
    ):
        from app.services.litellm import sync_user_team_memberships
        await sync_user_team_memberships(
            "user-1", "user@example.com", ["team-existing", "team-new"]
        )

    add.assert_awaited_once_with("user-1", "user@example.com", "team-new")
