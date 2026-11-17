"""Enforced equal groupTotal splits among signed-in members, applied to key caps."""

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import budget_enforcement as enforcement, budget_store, litellm, organization_key_policy as key_policy
from app.services import organization_store as store, organization_sync as sync


def tree(team_budget: dict) -> OrganizationHierarchy:
    return OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Department",
                    "groups": [
                        {
                            "members": [
                                {"name": "Engineering", "litellmTeamId": "eng", "userIds": ["ann", "ben", "cat"], "budget": team_budget},
                                {"name": "Sales", "litellmTeamId": "sales", "userIds": ["dan"], "budget": {"perUser": 7}},
                            ]
                        }
                    ],
                }
            ]
        }
    )


@pytest.fixture
def org(monkeypatch):
    def configure(team_budget=None, *, enforced=True):
        hierarchy = tree(team_budget or {"groupTotal": 90})
        monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
        monkeypatch.setattr(settings, "hierarchical_budgets_enforced", enforced)
        for user in ("ann", "ben", "cat", "dan"):
            store.remember(user, f"{user}@example.invalid", "explicit", [])
        return hierarchy

    monkeypatch.setattr(enforcement, "_spent", {})
    monkeypatch.setattr(enforcement, "_primed", False)
    monkeypatch.setattr(enforcement, "_snapshot", None)
    monkeypatch.setattr(enforcement, "_marked", set())
    yield configure


def cap(user: str) -> float | None:
    return sync.resolve_identity(store.get(user)).per_user


def join(*users: str) -> None:
    """Sign-in marks the participant, then refreshes the shares."""
    for user in users:
        enforcement.mark_participant(user)
    enforcement.refresh()


def test_total_is_split_equally_among_signed_in_members_and_updates_on_join(org):
    org()
    join("ann", "ben")
    # cat never signed in: nothing is reserved for her.
    assert (cap("ann"), cap("ben"), cap("cat")) == (45, 45, 0)
    join("cat")
    assert (cap("ann"), cap("ben"), cap("cat")) == (30, 30, 30)
    assert key_policy.key_policy(sync.resolve_identity(store.get("ann")))["max_budget"] == 30


def test_per_user_is_a_ceiling_and_unbudgeted_groups_keep_it(org):
    org({"groupTotal": 90, "perUser": 20})
    join("ann", "ben", "dan")
    assert (cap("ann"), cap("ben")) == (20, 20)
    assert cap("dan") == 7


def test_disabled_enforcement_keeps_fixed_per_user(org):
    org({"groupTotal": 90, "perUser": 20}, enforced=False)
    join("ann", "ben")
    assert cap("ann") == 20


def test_consumed_spend_is_never_reclaimed_by_a_new_member(org):
    org()
    join("ann", "ben")
    enforcement.observe_spend("ann", 80.0000001)
    # Spend floors are taken when the snapshot is rebuilt (e.g. on a join).
    enforcement._snapshot = None
    # ann already spent more than an equal share; ben gets only what remains.
    assert (cap("ann"), cap("ben")) == (80.000001, 9.999999)


def test_planning_page_override_and_envelope_are_enforced(org):
    hierarchy = org()
    join("ann", "ben", "cat")
    engineering = next(node for node in hierarchy.nodes.values() if node.team_id == "eng")
    budget_store.edit(0, lambda state: state.update(envelopes={engineering.id: 120_000_000}, overrides={"ann": 60_000_000}))
    enforcement.refresh()
    assert (cap("ann"), cap("ben"), cap("cat")) == (60, 30, 30)


@pytest.mark.asyncio
async def test_existing_key_holder_joins_the_split_before_their_key_is_capped(org, monkeypatch):
    org()
    join("ann")
    applied = {}

    async def apply(node, key):
        applied[key["token"]] = node.per_user

    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "ben-key", "spend": 5}]))
    monkeypatch.setattr(key_policy, "guard_ancestor_restrictions", AsyncMock())
    monkeypatch.setattr(key_policy, "apply_key", apply)
    monkeypatch.setattr(litellm, "add_team_member", AsyncMock())
    monkeypatch.setattr(sync.upstream, "team_info", AsyncMock(return_value={}))
    monkeypatch.setattr(sync.upstream, "membership", lambda info, user: {"user_id": user})
    await sync.sync_identity(store.get("ben"), {}, defer_finalization=True)
    # ben was never marked, but holding a key makes him a participant first.
    assert applied == {"ben-key": 45}
    assert "ben" in enforcement.participants()


@pytest.mark.asyncio
async def test_only_the_first_pass_lists_every_members_keys(org, monkeypatch):
    import asyncio

    org()
    listing = AsyncMock(return_value=[{"token": "k", "spend": 3}])
    monkeypatch.setattr(litellm, "list_user_keys", listing)
    users = ["ann", "ben", "cat"]
    await enforcement.observe_all(users, asyncio.Semaphore(5))
    assert listing.await_count == 3
    assert enforcement.participants() >= set(users)
    await enforcement.observe_all(users, asyncio.Semaphore(5))
    await enforcement.observe_all(users, asyncio.Semaphore(5))
    # Later passes rely on the regular sync's own listing: no extra requests.
    assert listing.await_count == 3


@pytest.mark.asyncio
async def test_disabled_enforcement_makes_no_extra_requests(org, monkeypatch):
    import asyncio

    org(enforced=False)
    listing = AsyncMock(return_value=[])
    monkeypatch.setattr(litellm, "list_user_keys", listing)
    await enforcement.observe_all(["ann"], asyncio.Semaphore(5))
    listing.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_budget_changes_survive_a_restart(org, monkeypatch):
    import asyncio

    hierarchy = org()
    join("ann", "ben", "cat")
    engineering = next(node for node in hierarchy.nodes.values() if node.team_id == "eng")
    budget_store.edit(0, lambda state: state.update(envelopes={engineering.id: 120_000_000}, overrides={"ann": 60_000_000}))
    enforcement.refresh()
    before = (cap("ann"), cap("ben"), cap("cat"))
    # A restart clears all process memory; only the database remains.
    monkeypatch.setattr(enforcement, "_spent", {})
    monkeypatch.setattr(enforcement, "_primed", False)
    monkeypatch.setattr(enforcement, "_snapshot", None)
    monkeypatch.setattr(enforcement, "_marked", set())
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    await enforcement.observe_all(["ann", "ben", "cat"], asyncio.Semaphore(5))
    assert (cap("ann"), cap("ben"), cap("cat")) == before == (60, 30, 30)


@pytest.mark.asyncio
async def test_a_sign_in_during_a_pass_never_changes_that_pass_or_caps_at_zero(org):
    import asyncio
    import contextvars

    from fastapi import HTTPException

    org()
    join("ann", "ben")
    token = await enforcement.pin()
    try:
        before = sync.resolve_identity(store.get("ann"))
        # cat signs in on another request while the pass is running.
        await asyncio.create_task(asyncio.to_thread(join, "cat"), context=contextvars.Context())
        # The pass keeps one consistent share, so its own check never fails.
        assert sync.resolve_identity(store.get("ann")) == before and before.per_user == 45
        # cat is not in the pinned shares: retry next pass, never a zero cap.
        with pytest.raises(HTTPException) as retry:
            sync.resolve_identity(store.get("cat"))
        assert retry.value.status_code == 409
    finally:
        enforcement.unpin(token)
    assert (cap("ann"), cap("ben"), cap("cat")) == (30, 30, 30)


def test_a_sync_error_does_not_remove_a_member_from_the_split(org):
    org()
    join("ann", "ben", "cat")
    store.failed("cat", "LiteLLM returned 502")
    enforcement._snapshot = None
    assert (cap("ann"), cap("ben"), cap("cat")) == (30, 30, 30)


@pytest.mark.asyncio
async def test_a_group_change_at_sign_in_gets_the_new_groups_share_not_zero(monkeypatch):
    hierarchy = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Department",
                    "groups": [
                        {
                            "members": [
                                {"name": "Eng", "litellmTeamId": "eng", "ssoGroups": ["eng"], "budget": {"groupTotal": 90}},
                                {"name": "Sales", "litellmTeamId": "sales", "ssoGroups": ["sales"], "budget": {"groupTotal": 40}},
                            ]
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    monkeypatch.setattr(settings, "hierarchical_budgets_enforced", True)
    monkeypatch.setattr(enforcement, "_snapshot", None)
    monkeypatch.setattr(enforcement, "_marked", set())
    monkeypatch.setattr(enforcement, "_spent", {})
    await sync.record_identity("ann", "ann@example.invalid", "sso", ["eng"])
    await sync.record_identity("bob", "bob@example.invalid", "sso", ["eng"])
    assert cap("ann") == 45
    await sync.record_identity("ann", "ann@example.invalid", "sso", ["sales"])
    assert (cap("ann"), cap("bob")) == (40, 90)


def test_spend_changes_alone_do_not_rewrite_caps(org):
    org()
    join("ann", "ben")
    snapshot = enforcement.refresh()
    enforcement.observe_spend("ann", 44)
    # Same members and budgets: the snapshot (and every key cap) is unchanged.
    assert enforcement.refresh() is snapshot
    assert (cap("ann"), cap("ben")) == (45, 45)


def test_an_older_rebuild_never_replaces_a_newer_one(org, monkeypatch):
    org()
    join("ann")
    original = enforcement.members
    calls = []

    def members():
        result = original()
        if not calls:
            calls.append(1)
            # A newer rebuild (cat signing in) completes while this one runs.
            join("cat")
        return result

    monkeypatch.setattr(enforcement, "members", members)
    enforcement._snapshot = None
    enforcement.refresh()
    monkeypatch.setattr(enforcement, "members", original)
    assert enforcement._snapshot["memberships"].keys() == {"ann", "cat"}
