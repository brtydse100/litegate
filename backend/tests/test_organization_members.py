"""Organization views share one resolved member list until an identity changes."""

from unittest.mock import patch

import pytest

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import organization_members as members
from app.services import organization_store as store
from tests.test_organization_config import example


@pytest.fixture(autouse=True)
def hierarchy(monkeypatch):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    return tree


@pytest.mark.asyncio
async def test_resolved_members_are_reused_until_an_identity_is_written():
    store.remember("ann", "ann@example.com", "sso", ["squad1"])
    with patch.object(store, "list_identities", wraps=store.list_identities) as listing:
        assert [row[1].member.name for row in await members.resolved()] == ["squad1"]
        await members.resolved()
        assert listing.call_count == 1
        store.remember("ben", "ben@example.com", "sso", ["squad2"])
        assert len(await members.resolved()) == 2
        assert listing.call_count == 2


@pytest.mark.asyncio
async def test_replaced_hierarchy_resolves_again(monkeypatch, hierarchy):
    store.remember("ann", "ann@example.com", "sso", ["squad1"])
    await members.resolved()
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy.bound({}))
    with patch.object(store, "list_identities", wraps=store.list_identities) as listing:
        await members.resolved()
    assert listing.call_count == 1


def test_member_counts_include_every_enclosing_group(hierarchy):
    squad1 = hierarchy.resolve("a", ["squad1"])
    squad2 = hierarchy.resolve("b", ["squad2"])
    marketing = next(node for node in hierarchy.roots if node.member.name == "Marketing")
    counts = members.member_counts([({}, squad1), ({}, squad2), ({}, marketing)])
    expected = {
        node.path: sum(member.path[: len(node.path)] == node.path for member in (squad1, squad2, marketing)) for node in hierarchy.nodes.values()
    }
    assert {node.path: counts[node.path] for node in hierarchy.nodes.values()} == expected
    assert counts[("Engineering",)] == 2
