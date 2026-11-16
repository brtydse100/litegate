"""Allocation conservation, spent reservations, and durable concurrent edits."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module, util

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize("value", ["1e999999", "1e-999999999", "1.000000000000000000000000000000001"])
def test_decimal_extremes_cannot_overflow_or_round_into_an_allocation(value):
    from app.services import budget_allocations

    with pytest.raises(HTTPException) as invalid:
        budget_allocations.units(value)
    assert invalid.value.status_code == 422


from app.organization import OrganizationHierarchy


@pytest.fixture
def tree():
    return OrganizationHierarchy.model_validate(
        {
            "levels": [
                {"name": "Division", "groups": [{"members": [{"name": "Root", "litellmTeamId": "root"}]}]},
                {"name": "Team", "groups": [{"parent": "Root", "members": [{"name": "Child"}]}]},
            ]
        }
    )


def module(name):
    assert util.find_spec(f"app.services.{name}") is not None, f"{name} must be implemented"
    return import_module(f"app.services.{name}")


def test_children_manual_zero_and_equal_direct_users_conserve_integer_units(tree):
    allocation = module("budget_allocations")
    root, child = tree.nodes.values()
    result = allocation.allocate(
        tree,
        {root.id: 101, child.id: 20},
        {"manual": 10, "zero": 0},
        {"manual": root.id, "zero": root.id, "auto1": root.id, "auto2": root.id, "nested": child.id},
    )
    assert result[root.id]["users"] == {"auto1": 35, "auto2": 35, "manual": 10, "zero": 0}
    assert result[root.id]["remainder"] == 1
    assert result[child.id]["users"] == {"nested": 20}
    assert result[root.id]["allocated"] == 100


def test_spent_removed_users_remain_reserved_and_new_children_default_zero(tree):
    allocation = module("budget_allocations")
    root, child = tree.nodes.values()
    result = allocation.allocate(tree, {root.id: 100}, {}, {"new": root.id}, {root.id: 30})
    assert result[root.id]["users"] == {"new": 70}
    assert result[child.id]["assigned"] == 0


def test_rejects_overallocation_including_descendant_and_spent_floors(tree):
    allocation = module("budget_allocations")
    root, child = tree.nodes.values()
    for envelopes, overrides, reservations in [
        ({root.id: 100, child.id: 101}, {}, {}),
        ({root.id: 100}, {"a": 101}, {}),
        ({root.id: 100}, {"a": 80}, {root.id: 30}),
    ]:
        with pytest.raises(HTTPException) as failed:
            allocation.allocate(tree, envelopes, overrides, {"a": root.id}, reservations)
        assert failed.value.status_code == 409


def test_precision_and_nonfinite_amounts_are_rejected():
    allocation = module("budget_allocations")
    assert allocation.units("1.000001") == 1000001
    for value in ["0.0000001", "NaN", "Infinity", "-1", True]:
        with pytest.raises(HTTPException):
            allocation.units(value)


def test_concurrent_revision_allows_only_one_writer_and_preserves_restart():
    store = module("budget_store")

    def update(value):
        try:
            return store.edit(0, lambda state: state["envelopes"].update({"root": value}))["revision"]
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, [10, 20]))
    assert sorted(results) == [1, 409]
    assert store.read()["revision"] == 1
    assert store.read()["envelopes"]["root"] in {10, 20}


def test_spend_observation_survives_transfer_and_rejects_stale_period():
    store = module("budget_store")
    store.observe("period-a", [{"user_id": "alice", "node_id": "old", "spent": 30}])
    store.observe("period-a", [{"user_id": "alice", "node_id": "new", "spent": 5}])
    assert store.reservations("period-a", {"alice": "new"}) == {"old": 30}
    assert store.reservations("period-b", {"alice": "new"}) == {}
    store.observe("period-a", [{"user_id": "alice", "node_id": "old", "spent": 10}])
    assert store.reservations("period-a", {}) == {"old": 30, "new": 5}
