import hashlib
import json
import sqlite3
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException, Response

from app.dependencies import get_current_user
from app.main import app
from app.models import CurrentUser, KeyDeleteRequest
from app.routers import keys
from app.services import audit, key_secrets, litellm, local_users

SECRET = "sk-synthetic-storage-test"
IDENTIFIER = hashlib.sha256(SECRET.encode()).hexdigest()
OWNER = CurrentUser(user_id="owner", email="owner@example.com")


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    for module in (keys, key_secrets, local_users, litellm):
        monkeypatch.setattr(module.settings, "save_api_keys_in_db", True)
        monkeypatch.setattr(module.settings, "local_users_db_path", str(tmp_path / "litegate.db"))
    local_users.init_db()


def test_storage_disabled_saves_no_secret(monkeypatch):
    monkeypatch.setattr(key_secrets.settings, "save_api_keys_in_db", False)
    key_secrets.save(SECRET, OWNER.user_id)
    with local_users.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM stored_api_keys").fetchone()[0] == 0
    assert key_secrets.get(IDENTIFIER, OWNER.user_id) is None


def test_storage_survives_reopen_and_matches_hashed_identifiers():
    key_secrets.save(SECRET, OWNER.user_id)
    assert key_secrets.get(IDENTIFIER, OWNER.user_id) == SECRET
    assert key_secrets.get(SECRET, OWNER.user_id) == SECRET
    assert key_secrets.get(IDENTIFIER, "someone-else") is None
    result = key_secrets.annotate([{"token": IDENTIFIER}, {"token": "older-key"}])
    assert result == [{"token": IDENTIFIER, "secret_available": True}, {"token": "older-key", "secret_available": False}]
    assert SECRET not in str(result)


@pytest.mark.parametrize("identifier", [SECRET, IDENTIFIER])
def test_deletion_removes_copy_even_when_storage_is_disabled(identifier, monkeypatch):
    key_secrets.save(SECRET, OWNER.user_id)
    monkeypatch.setattr(key_secrets.settings, "save_api_keys_in_db", False)
    key_secrets.remove(identifier)
    monkeypatch.setattr(key_secrets.settings, "save_api_keys_in_db", True)
    assert key_secrets.get(IDENTIFIER, OWNER.user_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [OWNER, CurrentUser(user_id="admin", email="admin@example.com", role="admin")])
async def test_owner_and_admin_can_reveal_with_secret_free_audit(user):
    key_secrets.save(SECRET, OWNER.user_id)
    response = Response()
    with patch.object(keys.llm, "get_key_info", new=AsyncMock(return_value={"user_id": OWNER.user_id})):
        result = await keys.reveal_key(KeyDeleteRequest(key=IDENTIFIER), response, user)
    assert result == {"key": SECRET}
    assert response.headers["Cache-Control"] == "no-store"
    events = audit.list_events(10)
    assert events[0]["action"] == "key.reveal"
    assert events[0]["actor_id"] == user.user_id
    assert SECRET not in str(events)
    assert IDENTIFIER not in str(events)


@pytest.mark.asyncio
async def test_another_user_cannot_reveal():
    key_secrets.save(SECRET, OWNER.user_id)
    other = CurrentUser(user_id="other", email="other@example.com")
    with (
        patch.object(keys.llm, "get_key_info", new=AsyncMock(return_value={"user_id": OWNER.user_id})),
        pytest.raises(HTTPException) as exc,
    ):
        await keys.reveal_key(KeyDeleteRequest(key=IDENTIFIER), Response(), other)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,info,stored", [(False, {"user_id": "owner"}, True), (True, None, True), (True, {"user_id": "owner"}, False)])
async def test_disabled_missing_and_older_keys_cannot_be_revealed(enabled, info, stored, monkeypatch):
    if stored:
        key_secrets.save(SECRET, OWNER.user_id)
    monkeypatch.setattr(keys.settings, "save_api_keys_in_db", enabled)
    with patch.object(keys.llm, "get_key_info", new=AsyncMock(return_value=info)), pytest.raises(HTTPException) as exc:
        await keys.reveal_key(KeyDeleteRequest(key=IDENTIFIER), Response(), OWNER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reveal_rejects_unauthenticated_and_virtual_key_callers():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for headers in ({}, {"Authorization": "Bearer sk-virtual-key"}, {"X-API-Key": "management-key"}):
            response = await client.post("/api/keys/reveal", json={"key": IDENTIFIER}, headers=headers)
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_reveal_keeps_cookie_csrf_protection():
    app.dependency_overrides[get_current_user] = lambda: OWNER
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", cookies={"litegate_session": "test-session"}
        ) as client:
            response = await client.post("/api/keys/reveal", json={"key": IDENTIFIER}, headers={"Origin": "https://other.example.com"})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def mock_litellm(request):
    if request.url.path == "/key/generate":
        return httpx.Response(200, json={"key": SECRET, "user_id": OWNER.user_id})
    return httpx.Response(200, json={"deleted": True})


@pytest.mark.asyncio
async def test_generation_and_deletion_use_shared_storage():
    with patch.object(litellm, "_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_litellm))):
        await litellm.generate_key(OWNER.user_id)
        assert key_secrets.get(IDENTIFIER, OWNER.user_id) == SECRET
        await litellm.delete_key(IDENTIFIER)
    assert key_secrets.get(IDENTIFIER, OWNER.user_id) is None


@pytest.mark.asyncio
async def test_failed_storage_revokes_new_key():
    with (
        patch.object(litellm, "_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_litellm))),
        patch.object(key_secrets, "save", side_effect=RuntimeError("database unavailable")),
        patch.object(litellm, "delete_key", new=AsyncMock()) as delete,
        pytest.raises(HTTPException) as exc,
    ):
        await litellm.generate_key(OWNER.user_id)
    assert exc.value.status_code == 503
    delete.assert_awaited_once_with(SECRET)


@pytest.mark.asyncio
async def test_regeneration_removes_old_copy_and_stores_replacement():
    old_secret = "sk-synthetic-old-key"
    old_identifier = key_secrets.key_hash(old_secret)
    key_secrets.save(old_secret, OWNER.user_id)
    with (
        patch.object(litellm, "_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_litellm))),
        patch.object(litellm, "list_user_keys", new=AsyncMock(return_value=[{"token": old_identifier, "spend": 2}])),
        patch("app.routers.keys.check_key_rate_limit"),
    ):
        result = await keys.regenerate_key(OWNER)
    assert result.key == SECRET
    assert key_secrets.get(old_identifier, OWNER.user_id) is None
    assert key_secrets.get(IDENTIFIER, OWNER.user_id) == SECRET


@pytest.mark.asyncio
async def test_failed_rotation_cleanup_removes_replacement_copy():
    old_secret = "sk-synthetic-old-key"
    old_identifier = key_secrets.key_hash(old_secret)
    key_secrets.save(old_secret, OWNER.user_id)

    def transport(request):
        if request.url.path == "/key/delete" and old_identifier in request.content.decode():
            return httpx.Response(500)
        return mock_litellm(request)

    with (
        patch.object(litellm, "_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport))),
        patch.object(litellm, "list_user_keys", new=AsyncMock(return_value=[{"token": old_identifier, "spend": 2}])),
        patch("app.routers.keys.check_key_rate_limit"),
        pytest.raises(HTTPException),
    ):
        await keys.regenerate_key(OWNER)
    assert key_secrets.get(old_identifier, OWNER.user_id) == old_secret
    assert key_secrets.get(IDENTIFIER, OWNER.user_id) is None


@pytest.mark.asyncio
async def test_database_cleanup_failure_preserves_working_replacement(caplog):
    old_secret = "sk-synthetic-old-key"
    old_identifier = key_secrets.key_hash(old_secret)
    key_secrets.save(old_secret, OWNER.user_id)
    active = {old_secret}
    deleted = []

    def transport(request):
        if request.url.path == "/key/generate":
            active.add(SECRET)
        elif request.url.path == "/key/delete":
            identifier = json.loads(request.content)["keys"][0]
            active.discard(old_secret if identifier == old_identifier else identifier)
            deleted.append(identifier)
        return mock_litellm(request)

    with (
        patch.object(litellm, "_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport))),
        patch.object(litellm, "list_user_keys", new=AsyncMock(return_value=[{"token": old_identifier, "spend": 2}])),
        patch.object(key_secrets, "remove", side_effect=sqlite3.OperationalError(f"database is locked: {old_secret}")),
        patch("app.routers.keys.check_key_rate_limit"),
    ):
        result = await keys.regenerate_key(OWNER)

    assert result.key == SECRET
    assert active == {SECRET}
    assert deleted == [old_identifier]
    assert key_secrets.get(IDENTIFIER, OWNER.user_id) == SECRET
    assert key_secrets.get(old_identifier, OWNER.user_id) == old_secret
    assert "cleanup failed after successful LiteLLM revocation" in caplog.text
    assert old_secret not in caplog.text
    assert old_identifier not in caplog.text
    assert SECRET not in caplog.text
    with patch.object(litellm, "get_key_info", new=AsyncMock(return_value=None)), pytest.raises(HTTPException) as exc:
        await keys.reveal_key(KeyDeleteRequest(key=old_identifier), Response(), OWNER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_failed_save_still_revokes_new_key_when_database_cleanup_fails():
    deleted = []

    def transport(request):
        if request.url.path == "/key/delete":
            deleted.extend(json.loads(request.content)["keys"])
        return mock_litellm(request)

    with (
        patch.object(litellm, "_client", side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport))),
        patch.object(key_secrets, "save", side_effect=sqlite3.OperationalError("database is locked")),
        patch.object(key_secrets, "remove", side_effect=sqlite3.OperationalError("database is locked")),
        pytest.raises(HTTPException) as exc,
    ):
        await litellm.generate_key(OWNER.user_id)

    assert exc.value.status_code == 503
    assert deleted == [SECRET]
