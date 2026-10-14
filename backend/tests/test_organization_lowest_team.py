"""Real team ownership and per-key allowance contracts for the combined hierarchy."""

import json

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, litellm_client, organization_reports as reports, organization_store as store, organization_sync as sync
from tests.test_organization_config import example


@pytest_asyncio.fixture
async def native(monkeypatch, tmp_path):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "native.db"))
    sync._locks.clear()
    state = {
        "teams": {"engineering": {"team_id": "engineering", "max_budget": 5000, "budget_duration": "30d", "spend": 5}},
        "keys": {
            "key-old": {"token": "key-old", "user_id": "alice", "team_id": "engineering", "max_budget": None, "budget_duration": None, "spend": 42}
        },
        "members": {},
        "user_budget": 25,
        "calls": [],
        "ignore_key_budget": False,
    }

    def handle(request):
        path = request.url.path
        data = json.loads(request.content) if request.content else {}
        state["calls"].append((request.method, path, data))
        team_id = data.get("team_id") or request.url.params.get("team_id")
        if path == "/v2/team/list":
            team = state["teams"].get(team_id)
            return httpx.Response(200, json={"teams": [team] if team else [], "total": int(team is not None), "total_pages": 1})
        if path == "/team/new":
            state["teams"][team_id] = {**data, "spend": 0}
            return httpx.Response(200, json=data)
        if path == "/team/update":
            state["teams"][team_id].update(data)
            return httpx.Response(200, json=state["teams"][team_id])
        if path == "/team/member_add":
            state["members"].setdefault((team_id, data["member"]["user_id"]), {"max_budget": 30, "rpm_limit": 10})
            return httpx.Response(200, json={})
        if path == "/team/member_update":
            state["members"].setdefault((team_id, data["user_id"]), {})["max_budget"] = data["max_budget_in_team"]
            return httpx.Response(200, json=data)
        if path == "/team/info":
            members = [
                {"user_id": owner, "spend": 42, "litellm_budget_table": budget} for (tid, owner), budget in state["members"].items() if tid == team_id
            ]
            if state.get("bad_member_record") and members:
                members = [{"user_id": "alice", **state["bad_member_record"]}]
            return httpx.Response(
                200,
                json={
                    "team_info": {
                        **state["teams"][team_id],
                        "members_with_roles": [{"user_id": item["user_id"], "role": "user"} for item in members]
                        + state.get("roster_only", {}).get(team_id, []),
                    },
                    "team_memberships": members,
                },
            )
        if path == "/user/info":
            owner = request.url.params.get("user_id")
            return httpx.Response(
                200,
                json={
                    "user_id": owner,
                    "user_info": {"max_budget": state["user_budget"]},
                    "keys": [key for key in state["keys"].values() if key["user_id"] == owner],
                },
            )
        if path == "/user/update":
            state["user_budget"] = data["max_budget"]
            return httpx.Response(200, json=data)
        if path == "/key/info":
            return httpx.Response(200, json={"info": state["keys"].get(request.url.params["key"])})
        if path == "/key/update":
            changes = {key: value for key, value in data.items() if key != "key" and not (key == "max_budget" and state["ignore_key_budget"])}
            state["keys"][data["key"]].update(changes)
            if data["key"] == "key-new" and state.get("corrupt_new_owner"):
                state["keys"]["key-new"]["user_id"] = "another-owner"
            return httpx.Response(200, json=state["keys"][data["key"]])
        if path == "/key/list":
            keys = [key for key in state["keys"].values() if not team_id or key["team_id"] == team_id]
            return httpx.Response(200, json={"keys": keys, "total_count": len(keys), "current_page": 1, "total_pages": 1})
        if path == "/key/generate":
            state["keys"]["key-new"] = {"token": "key-new", "spend": data.get("spend", 0), **data}
            if state.get("corrupt_new_owner"):
                state["keys"]["key-new"]["max_budget"] = 5
            return httpx.Response(200, json={"key": "key-new", "user_id": data["user_id"]})
        if path == "/key/delete":
            for key in data["keys"]:
                state["keys"].pop(key, None)
            return httpx.Response(200, json={})
        raise AssertionError(f"Unexpected upstream path: {path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(litellm_client, "_shared_client", client)
        yield tree, state


def test_each_level_has_a_distinct_stable_team_and_deepest_match_owns_the_key():
    tree = OrganizationHierarchy.model_validate(example())
    root, middle, leaf = (tree.resolve("alice", groups) for groups in (["engineers"], ["digital"], ["squad1"]))
    assert len({root.team_id, middle.team_id, leaf.team_id}) == 3
    assert tree.resolve("alice", ["engineers", "digital", "squad1"]).team_id == leaf.team_id
    assert all(tree.is_managed_team(node.team_id) for node in tree.nodes.values())


@pytest.mark.asyncio
async def test_ancestor_key_migrates_to_lowest_team_without_resetting_spend(native):
    tree, state = native
    node = await sync.remember("alice", "alice@example.com", "sso", ["engineers", "digital", "squad1"])
    key = state["keys"]["key-old"]
    assert key["team_id"] == tree.resolve("alice", ["squad1"]).team_id == node.team_id
    assert key["max_budget"] == 100
    assert key["budget_duration"] == "30d"
    assert key["spend"] == 42
    assert state["user_budget"] is None
    assert state["members"][(node.team_id, "alice")]["max_budget"] is None
    assert state["members"][(node.team_id, "alice")]["rpm_limit"] == 10
    await sync.reconcile()
    assert state["teams"]["engineering"]["max_budget"] is None
    assert state["teams"]["engineering"]["spend"] == 5


@pytest.mark.asyncio
async def test_key_budget_must_be_verified_before_individual_user_caps_are_removed(native):
    _, state = native
    state["ignore_key_budget"] = True
    with pytest.raises(HTTPException):
        await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    assert state["user_budget"] == 25
    assert not any(path == "/user/update" for _, path, _ in state["calls"])


@pytest.mark.asyncio
async def test_unmanaged_sibling_credential_blocks_automatic_allowance_removal(native):
    _, state = native
    state["keys"]["foreign"] = {"token": "foreign", "user_id": "alice", "team_id": "manual", "max_budget": None, "spend": 0}
    with pytest.raises(HTTPException):
        await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    assert state["user_budget"] == 25
    assert state["keys"]["key-old"]["max_budget"] is None


@pytest.mark.asyncio
async def test_new_key_and_rotation_use_lowest_team_and_carry_key_spend(native):
    tree, state = native
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    result = await sync.generate_key("alice", "alice@example.com", "engineering", initial_spend=42)
    new = state["keys"][result["key"]]
    assert new["team_id"] == tree.resolve("alice", ["squad1"]).team_id
    assert new["max_budget"] == 100
    assert new["spend"] == 42


@pytest.mark.asyncio
async def test_parent_spend_sums_each_descendant_team_once(native):
    tree, state = native
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    middle = tree.resolve("alice", ["digital"])
    leaf = tree.resolve("alice", ["squad1"])
    state["teams"][middle.team_id]["spend"] = 7
    state["teams"][leaf.team_id]["spend"] = 11
    # Provision unrelated zero-spend groups without introducing duplicate spends.
    await sync.reconcile()
    groups = {tuple(group["path"]): group for group in (await reports.overview())["groups"]}
    assert groups[("Engineering",)]["group_spend"] == 23
    assert groups[("Engineering", "Digital")]["group_spend"] == 18
    assert groups[("Engineering", "Digital", "squad1")]["group_spend"] == 11
    assert groups[("Engineering",)]["group_total"] == 5000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record", [{"budget_id": "hidden", "litellm_budget_table": None}, {"litellm_budget_table": {}}, {"litellm_budget_table": []}]
)
async def test_incomplete_member_budget_verification_keeps_the_personal_cap(native, record):
    _, state = native
    state["bad_member_record"] = record
    with pytest.raises(HTTPException):
        await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    assert state["user_budget"] == 25
    assert store.get("alice")["sync_error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("group, allowance", [("squad1", 100), ("squad2", 50), ("unlimited", None), ("blocked", 0)])
async def test_inherited_null_and_zero_allowances_are_applied_to_keys(native, group, allowance):
    tree, state = native
    await sync.remember("alice", "alice@example.com", "sso", [group])
    assert state["keys"]["key-old"]["max_budget"] == allowance
    assert state["keys"]["key-old"]["team_id"] == tree.resolve("alice", [group]).team_id


@pytest.mark.asyncio
async def test_unknown_root_credential_prevents_removal_of_its_existing_shared_cap(native):
    _, state = native
    state["keys"]["unknown"] = {
        "token": "unknown",
        "user_id": "external-owner",
        "team_id": "engineering",
        "max_budget": None,
        "budget_duration": None,
        "spend": 3,
    }
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    await sync.reconcile()
    assert state["teams"]["engineering"]["max_budget"] == 5000
    assert state["keys"]["unknown"]["max_budget"] is None


@pytest.mark.asyncio
async def test_allowance_only_edits_preserve_key_spend_and_reset_window(native):
    tree, state = native
    node = tree.resolve("alice", ["squad1"])
    state["keys"]["key-old"].update(team_id=node.team_id, max_budget=50, budget_duration="30d", budget_reset_at="2026-11-01T00:00:00Z")
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    updates = [data for _, path, data in state["calls"] if path == "/key/update"]
    assert updates == [{"key": "key-old", "max_budget": 100}]
    assert state["keys"]["key-old"]["budget_reset_at"] == "2026-11-01T00:00:00Z"
    assert state["keys"]["key-old"]["spend"] == 42


@pytest.mark.asyncio
async def test_wrong_owner_after_upstream_default_correction_revokes_the_undelivered_key(native):
    _, state = native
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    state["corrupt_new_owner"] = True
    with pytest.raises(HTTPException):
        await sync.generate_key("alice", "alice@example.com", None, initial_spend=42)
    assert "key-new" not in state["keys"]
    assert "key-old" in state["keys"]


@pytest.mark.asyncio
async def test_concurrent_creation_does_not_issue_two_unique_keys(native):
    import asyncio

    _, state = native
    state["keys"].clear()
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    results = await asyncio.gather(*(sync.generate_key("alice", "alice@example.com", None) for _ in range(2)), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    assert sum(path == "/key/generate" for _, path, _ in state["calls"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction", [{"models": ["approved-model"]}, {"blocked": True}, {"rpm_limit": 10}, {"tpm_limit": 100}])
async def test_ancestor_restrictions_cannot_silently_disappear_on_a_leaf(native, restriction):
    _, state = native
    state["teams"]["engineering"].update(restriction)
    with pytest.raises(HTTPException, match="ancestor.*restrictions"):
        await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    assert state["keys"]["key-old"]["team_id"] == "engineering"
    assert state["user_budget"] == 25
    assert not any(path == "/key/update" for _, path, _ in state["calls"])


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction", [{"allowed_models": ["approved-model"]}, {"rpm_limit": 0}, {"budget_id": "linked"}])
async def test_source_member_restrictions_must_be_verified_before_moving_a_key(native, restriction):
    _, state = native
    state["members"][("engineering", "alice")] = {"max_budget": 25}
    state["bad_member_record"] = {"litellm_budget_table": {"max_budget": 25}, **restriction}
    if "budget_id" in restriction:
        state["bad_member_record"]["litellm_budget_table"] = None
    with pytest.raises(HTTPException):
        await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    assert state["keys"]["key-old"]["team_id"] == "engineering"
    assert state["user_budget"] == 25


@pytest.mark.asyncio
async def test_uncapped_roster_only_source_member_can_migrate_to_the_lowest_team(native):
    tree, state = native
    state["roster_only"] = {"engineering": [{"user_id": "alice", "role": "user"}]}
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    assert state["keys"]["key-old"]["team_id"] == tree.resolve("alice", ["squad1"]).team_id
