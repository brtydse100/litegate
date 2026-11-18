"""Members with enforced organization budgets replace their own key safely."""

import asyncio
import copy

import pytest
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import key_rotation_freeze as freeze, litellm, organization_store, organization_sync as sync


class FakeLiteLLM:
    def __init__(self, keys):
        self.keys = {key["token"]: key for key in copy.deepcopy(keys)}

    async def list_user_keys(self, user_id):
        return [copy.deepcopy(key) for key in self.keys.values() if key["user_id"] == user_id]

    async def get_key_info(self, token):
        return copy.deepcopy(self.keys.get(token))

    async def update_key(self, token, changes):
        self.keys[token].update(copy.deepcopy(changes))
        return {}


@pytest.fixture
def litellm_keys(monkeypatch):
    monkeypatch.setattr(settings, "hierarchical_budgets_enforced", True)
    monkeypatch.setattr(
        settings,
        "organization_hierarchy",
        OrganizationHierarchy.model_validate(
            {"levels": [{"name": "Group", "groups": [{"members": [{"name": "Eng", "litellmTeamId": "eng", "budget": {"groupTotal": 90}}]}]}]}
        ),
    )
    monkeypatch.setattr(freeze, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(freeze, "active", set())
    organization_store.remember("ann", "ann@example.invalid", "sso", [])

    def install(*keys):
        fake = FakeLiteLLM(keys)
        for name in ("list_user_keys", "get_key_info", "update_key"):
            monkeypatch.setattr(litellm, name, getattr(fake, name))
        return fake

    return install


def key(token="old", team="eng", **extra):
    return {"token": token, "user_id": "ann", "team_id": team, "spend": 1.5, "blocked": False, "metadata": {"note": "x"}, **extra}


@pytest.mark.asyncio
async def test_replacement_runs_only_after_the_old_key_is_paused(litellm_keys, monkeypatch):
    fake = litellm_keys(key())
    seen = {}

    async def replace(*args, **kwargs):
        seen["blocked"] = fake.keys["old"]["blocked"]
        seen["original"] = freeze.original(fake.keys["old"])
        del fake.keys["old"]
        return {"key": "new"}

    monkeypatch.setattr(sync, "_rotate_key", replace)
    assert (await sync.rotate_key("ann", "ann@example.invalid", None, key_alias="ann's key"))["key"] == "new"
    assert seen["blocked"] is True
    # Policy checks compare the key as it was before the pause.
    assert seen["original"]["blocked"] is False and seen["original"]["metadata"] == {"note": "x"}
    assert freeze.active == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_a_failed_replacement_restores_the_old_key(litellm_keys, monkeypatch, blocked):
    fake = litellm_keys(key(blocked=blocked))
    monkeypatch.setattr(sync, "_rotate_key", lambda *a, **k: (_ for _ in ()).throw(HTTPException(502, "upstream")))
    with pytest.raises(HTTPException):
        await sync.rotate_key("ann", "", None, key_alias="ann's key")
    # An administrator's block is kept; a pause added by the rotation is lifted.
    assert fake.keys["old"]["blocked"] is blocked
    assert fake.keys["old"]["metadata"] == {"note": "x"}


@pytest.mark.asyncio
async def test_a_second_concurrent_replacement_is_rejected(litellm_keys, monkeypatch):
    litellm_keys(key())
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await release.wait()
        return {"key": "new"}

    monkeypatch.setattr(sync, "_rotate_key", slow)
    first = asyncio.create_task(sync.rotate_key("ann", "", None, key_alias="k"))
    await started.wait()
    with pytest.raises(HTTPException) as error:
        await sync.rotate_key("ann", "", None, key_alias="k")
    assert error.value.status_code == 409
    release.set()
    assert (await first)["key"] == "new"


@pytest.mark.asyncio
async def test_several_managed_keys_are_refused_before_anything_changes(litellm_keys, monkeypatch):
    fake = litellm_keys(key("one"), key("two"))
    monkeypatch.setattr(sync, "_rotate_key", lambda *a, **k: pytest.fail("must not replace"))
    with pytest.raises(HTTPException) as error:
        await sync.rotate_key("ann", "", None, key_alias="k")
    assert error.value.status_code == 409
    assert not any(record["blocked"] for record in fake.keys.values())


@pytest.mark.asyncio
async def test_an_unknown_membership_asks_to_sign_in_before_anything_changes(litellm_keys, monkeypatch):
    fake = litellm_keys({**key(), "user_id": "bob"})
    monkeypatch.setattr(sync, "_rotate_key", lambda *a, **k: pytest.fail("must not replace"))
    with pytest.raises(HTTPException) as error:
        await sync.rotate_key("bob", "", None, key_alias="k")
    assert error.value.status_code == 409 and "sign in again" in error.value.detail
    assert fake.keys["old"]["blocked"] is False


@pytest.mark.asyncio
async def test_unmanaged_keys_are_replaced_without_a_pause(litellm_keys, monkeypatch):
    fake = litellm_keys(key("one", team="other"), key("two", team=None))

    async def replace(*args, **kwargs):
        assert not any(record["blocked"] for record in fake.keys.values())
        return {"key": "new"}

    monkeypatch.setattr(sync, "_rotate_key", replace)
    monkeypatch.setattr(freeze, "settle", lambda: pytest.fail("no pause needed"))
    assert (await sync.rotate_key("ann", "", None, key_alias="k"))["key"] == "new"


@pytest.mark.asyncio
async def test_an_interrupted_pause_is_lifted_on_the_next_sync(litellm_keys):
    fake = litellm_keys(key())
    assert await freeze.freeze("ann", await litellm.list_user_keys("ann"))
    freeze.active.add("ann")
    # A rotation still running in this process keeps its pause.
    assert (await freeze.recover("ann", await litellm.list_user_keys("ann")))[0]["blocked"] is True
    freeze.active.clear()
    # After a restart nothing is running, so the pause is lifted.
    recovered = await freeze.recover("ann", await litellm.list_user_keys("ann"))
    assert recovered[0]["blocked"] is False and fake.keys["old"]["blocked"] is False
    assert fake.keys["old"]["metadata"] == {"note": "x"}
