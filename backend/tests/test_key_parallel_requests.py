import json
from contextlib import asynccontextmanager

import httpx
import pytest
from pydantic import ValidationError

from app import config
from app.services import litellm, organization_client


def test_parallel_request_default_is_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path)
    monkeypatch.delenv("KEY_MAX_PARALLEL_REQUESTS", raising=False)
    assert config.Settings().key_max_parallel_requests is None


def test_parallel_request_default_loads_yaml_and_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path)
    monkeypatch.delenv("KEY_MAX_PARALLEL_REQUESTS", raising=False)
    (tmp_path / "config.yaml").write_text("key_max_parallel_requests: 10\n")
    assert config.Settings().key_max_parallel_requests == 10

    monkeypatch.setenv("KEY_MAX_PARALLEL_REQUESTS", "20")
    assert config.Settings().key_max_parallel_requests == 20


@pytest.mark.parametrize("value", [0, -1, "invalid", 1.5])
def test_invalid_parallel_request_default_is_rejected(value):
    with pytest.raises(ValidationError):
        config.Settings(key_max_parallel_requests=value)


@pytest.mark.parametrize("limit", [None, 1, 10])
@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("replacement", [False, True])
async def test_generated_key_parallel_default_reaches_litellm(monkeypatch, limit, managed, replacement):
    for service in (litellm, organization_client):
        monkeypatch.setattr(service.settings, "key_max_parallel_requests", limit)
        monkeypatch.setattr(service.settings, "save_api_keys_in_db", False)
    generated = []

    def handle(request):
        if request.url.path == "/key/generate":
            generated.append(json.loads(request.content))
            return httpx.Response(200, json={"key": "sk-test-parallel"})
        assert request.url.path == "/key/info"
        return httpx.Response(200, json={"info": generated[-1]})

    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as pooled:
            yield pooled

    monkeypatch.setattr(litellm, "_client", client)
    monkeypatch.setattr(organization_client, "client", client)
    options = {"initial_spend": 4.25, "key_alias": "replacement"} if replacement else {}
    if managed:
        result = await organization_client.generate_key("u", "user@example.com", "team", max_budget=25, budget_duration="30d", **options)
    else:
        result = await litellm.generate_key("u", "user@example.com", "team", **options)

    assert result["key"] == "sk-test-parallel"
    assert len(generated) == 1
    payload = generated[0]
    assert payload["user_id"] == "u"
    assert payload["team_id"] == "team"
    if limit is None:
        assert "max_parallel_requests" not in payload
    else:
        assert payload["max_parallel_requests"] == limit
    if replacement:
        assert payload["spend"] == 4.25
        assert payload["key_alias"] == "replacement"
    if managed:
        assert payload["max_budget"] == 25
        assert payload["budget_duration"] == "30d"
