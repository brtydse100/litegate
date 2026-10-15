"""Public contracts for explicitly moving individual allowances onto keys."""

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.models import CurrentUser
from app.rate_limit import _key_ops
from app.routers.api_actor import ApiActor, get_api_actor
from app.services import litellm_client


@pytest_asyncio.fixture
async def upstream(monkeypatch):
    state = {
        "user_budget": 25,
        "member_budget": 30,
        "key_budget": 50,
        "fail_member": False,
        "ignore_user_clear": False,
        "ignore_member_clear": False,
        "ignore_key_update": False,
        "team_id": "devops",
        "owner": "alice",
        "calls": [],
    }

    def handler(request):
        import json

        path = request.url.path
        payload = json.loads(request.content) if request.content else {}
        state["calls"].append((request.method, path, payload))
        if path == "/key/info":
            if request.url.params.get("key") == "sk-replacement":
                return httpx.Response(200, json={"info": state["generated"]})
            return httpx.Response(200, json={"info": {"user_id": state["owner"], "team_id": state["team_id"], "max_budget": state["key_budget"]}})
        if path == "/key/update":
            if payload["key"] == "sk-replacement":
                if not state.get("ignore_replacement_budget"):
                    state["generated"].update(payload)
                return httpx.Response(200, json=payload)
            if not state["ignore_key_update"]:
                state["key_budget"] = payload.get("max_budget", state["key_budget"])
            return httpx.Response(200, json=payload)
        if path == "/key/generate":
            state["generated"] = {"token": "sk-replacement", **payload}
            return httpx.Response(200, json={"key": "sk-replacement"})
        if path == "/key/delete":
            state.setdefault("deleted", []).extend(payload["keys"])
            return httpx.Response(200, json={})
        if path == "/user/update":
            if not state["ignore_user_clear"]:
                state["user_budget"] = payload["max_budget"]
            return httpx.Response(200, json=payload)
        if path == "/user/info":
            return httpx.Response(
                200,
                json={
                    "user_info": {"max_budget": state["user_budget"]},
                    "keys": state.get("owner_keys", [{"token": "key-1", "max_budget": state["key_budget"], "budget_duration": "30d", "spend": 20}]),
                },
            )
        if path == "/team/member_update":
            if state["fail_member"]:
                return httpx.Response(400, json={"error": "unsupported"})
            if not state["ignore_member_clear"]:
                state["member_budget"] = payload["max_budget_in_team"]
            return httpx.Response(200, json=payload)
        if path == "/team/info":
            return httpx.Response(
                200,
                json={
                    "team_info": {"max_budget": 2000, **state.get("team_info", {})},
                    "team_memberships": state.get(
                        "memberships", [{"user_id": "alice", "litellm_budget_table": {"max_budget": state["member_budget"]}}]
                    ),
                },
            )
        if path == "/model/info":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_name": "model-b", "litellm_params": {"api_key": "must-not-leak"}},
                        {"model_name": "model-a"},
                        {"model_name": "model-b"},
                    ]
                },
            )
        raise AssertionError(f"Unexpected upstream request: {path}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(litellm_client, "_shared_client", client)
    _key_ops.clear()
    yield state
    await client.aclose()
    app.dependency_overrides.clear()


def actor(role):
    app.dependency_overrides[get_api_actor] = lambda: ApiActor(CurrentUser(user_id="admin", email="admin@example.com", role=role))


@pytest.mark.asyncio
async def test_admin_can_make_key_budget_the_individual_allowance(upstream):
    actor("admin")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert upstream["key_budget"] == 150
    assert upstream["user_budget"] is None
    assert upstream["member_budget"] is None
    assert all(path != "/team/update" for _, path, _ in upstream["calls"])


@pytest.mark.asyncio
async def test_normal_key_edits_preserve_external_user_budgets(upstream):
    actor("admin")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}})
    assert response.json()["updated"] == 1
    assert upstream["user_budget"] == 25
    assert upstream["member_budget"] == 30


@pytest.mark.asyncio
async def test_policy_requires_a_finite_key_cap_before_removing_user_caps(upstream):
    actor("admin")
    upstream["key_budget"] = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"rpm_limit": 100}, "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert upstream["user_budget"] == 25
    assert upstream["member_budget"] == 30


@pytest.mark.asyncio
async def test_unsupported_member_budget_removal_is_reported_as_failure(upstream):
    actor("admin")
    upstream["fail_member"] = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert "error" in response.json()["results"][0]


@pytest.mark.asyncio
async def test_non_admin_cannot_remove_user_caps(upstream):
    actor("user")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.status_code == 403
    assert upstream["calls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ignored", ["ignore_user_clear", "ignore_member_clear"])
async def test_silently_ignored_budget_removals_are_not_reported_as_success(upstream, ignored):
    actor("admin")
    upstream[ignored] = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert "incomplete" in response.json()["results"][0]["error"]


@pytest.mark.asyncio
async def test_ignored_key_budget_update_keeps_both_individual_caps(upstream):
    actor("admin")
    upstream["ignore_key_update"] = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert upstream["user_budget"] == 25
    assert upstream["member_budget"] == 30


@pytest.mark.asyncio
async def test_standalone_key_only_clears_its_owners_personal_budget(upstream):
    actor("admin")
    upstream["team_id"] = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.json()["updated"] == 1
    assert upstream["user_budget"] is None
    assert upstream["member_budget"] == 30


@pytest.mark.asyncio
async def test_ownerless_key_is_rejected_before_any_mutations(upstream):
    actor("admin")
    upstream["owner"] = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert all(method == "GET" for method, _, _ in upstream["calls"])


@pytest.mark.asyncio
async def test_multiple_owner_keys_prevent_removal_of_the_shared_user_cap(upstream):
    actor("admin")
    upstream["owner_keys"] = [{"token": "key-1", "max_budget": 50}, {"token": "key-2", "max_budget": None}]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert upstream["user_budget"] == 25
    assert upstream["member_budget"] == 30


@pytest.mark.asyncio
async def test_missing_membership_evidence_does_not_report_success(upstream):
    actor("admin")
    upstream["memberships"] = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 150}, "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert upstream["user_budget"] == 25


@pytest.mark.asyncio
async def test_existing_finite_key_can_be_migrated_without_changing_its_settings(upstream):
    actor("admin")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "use_key_budget_only": True})
    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert upstream["key_budget"] == 50
    assert upstream["user_budget"] is None
    assert upstream["member_budget"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("budget_record", [[], "invalid"])
async def test_malformed_membership_budget_is_not_treated_as_verified_removal(upstream, budget_record):
    actor("admin")
    upstream["memberships"] = [{"user_id": "alice", "litellm_budget_table": budget_record}]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "use_key_budget_only": True})
    assert response.json()["failed"] == 1
    assert upstream["user_budget"] == 25


@pytest.mark.asyncio
@pytest.mark.parametrize("role, status", [("admin", 200), ("user", 403)])
async def test_model_choices_are_admin_only_and_exclude_provider_secrets(upstream, role, status):
    actor(role)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/models")
    assert response.status_code == status
    if status == 200:
        assert response.json() == {"models": ["model-a", "model-b"]}
