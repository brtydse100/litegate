"""Exercise the manual helper against LiteGate's real management authentication."""

from contextlib import closing
import importlib.util
import io
import urllib.error
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.rate_limit import _key_ops
from app.services import litellm, local_users

spec = importlib.util.spec_from_file_location("local_test_helper", Path(__file__).resolve().parents[2] / "scripts/local_test.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def portal(monkeypatch, tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/config.yaml").write_text("organizationHierarchy:\n  levels: []\n")
    monkeypatch.setattr(helper, "ROOT", tmp_path)
    monkeypatch.setattr(settings, "management_api_key", "synthetic-management-key")
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "users.db"))
    monkeypatch.setattr(litellm, "ensure_user_exists", AsyncMock(return_value={}))
    _key_ops.clear()
    local_users.init_db()
    browser = TestClient(app)

    def urlopen(request, timeout):
        response = browser.request(request.get_method(), request.full_url, content=request.data, headers=dict(request.header_items()))
        if response.status_code >= 400:
            raise urllib.error.HTTPError(request.full_url, response.status_code, response.reason_phrase, {}, io.BytesIO(response.content))
        return closing(io.BytesIO(response.content))

    monkeypatch.setattr(helper.urllib.request, "urlopen", urlopen)
    yield
    browser.close()
    _key_ops.clear()


def test_management_calls_can_list_and_create_local_users(portal):
    assert helper.call(helper.PORTAL, "/api/v1/users", key="synthetic-management-key") == []
    user = helper.call(
        helper.PORTAL,
        "/api/v1/users",
        key="synthetic-management-key",
        payload={"username": "alice", "email": "alice@example.invalid", "password": "synthetic-local-password", "role": "user"},
    )
    assert user["user_id"] == "local:alice"
    assert len(helper.call(helper.PORTAL, "/api/v1/users", key="synthetic-management-key")) == 1


def test_partial_start_can_resume_without_launching_another_backend(portal, monkeypatch):
    access = {"password": "synthetic-local-password", "jwt": "unused", "management": "synthetic-management-key"}
    monkeypatch.setattr(helper, "state", lambda: access)
    monkeypatch.setattr(helper.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(helper, "ready", lambda *args: True)
    monkeypatch.setattr(helper, "wait_ready", lambda *args: None)

    def no_launch(*args):
        pytest.fail("An authenticated running instance must be reused")

    monkeypatch.setattr(helper, "launch", no_launch)
    helper.start()
    helper.start()
    assert {user["username"] for user in local_users.list_users()} == {"alice", "bob", "carol"}


def test_start_rejects_a_different_running_instance_without_seeding(portal, monkeypatch):
    monkeypatch.setattr(helper, "state", lambda: {"password": "unused", "jwt": "unused", "management": "wrong-instance-key"})
    monkeypatch.setattr(helper.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(helper, "ready", lambda *args: True)
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value=None))
    monkeypatch.setattr(helper, "launch", lambda *args: pytest.fail("Do not launch anything for an unrecognized instance"))
    with pytest.raises(RuntimeError, match="Cannot authenticate.*401"):
        helper.start()
    assert local_users.list_users() == []


@pytest.mark.parametrize(
    "message, expected",
    [
        ("OpenrouterException: User not found; sensitive-provider-secret", "OpenRouter rejected"),
        ("Invalid virtual key sensitive-provider-secret", "LiteLLM rejected"),
    ],
)
def test_request_distinguishes_provider_auth_from_virtual_key_auth(monkeypatch, capsys, message, expected):
    import json

    monkeypatch.setenv("LITEGATE_TEST_KEY", "synthetic-user-secret")

    def rejected(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:4000/v1/chat/completions", 401, "Unauthorized", {}, io.BytesIO(json.dumps({"error": {"message": message}}).encode())
        )

    monkeypatch.setattr(helper, "call", rejected)
    with pytest.raises(SystemExit):
        helper.request(SimpleNamespace(count=1, model="free-router", prompt="hello", max_tokens=8))
    output = capsys.readouterr().out
    assert expected in output
    assert "sensitive-provider-secret" not in output
    assert "synthetic-user-secret" not in output


def test_request_reports_litellm_accounting_separately_from_provider_cost(monkeypatch, capsys):
    monkeypatch.setenv("LITEGATE_TEST_KEY", "synthetic-user-secret")

    def completion(*args, **kwargs):
        kwargs["response_headers"]["x-litellm-response-cost"] = "0.0024"
        return {"choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 24, "cost": 0}}

    monkeypatch.setattr(helper, "call", completion)
    helper.request(SimpleNamespace(count=1, model="free-2", prompt="hello", max_tokens=8))
    output = capsys.readouterr().out
    assert "LiteLLM accounted cost: $0.002400" in output
    assert "synthetic-user-secret" not in output
