from unittest.mock import AsyncMock, Mock

import pytest

from app import main
from app.config import settings
from app.services.organization_mapping import load_mapping


@pytest.fixture
def lifecycle(monkeypatch):
    started, closed = AsyncMock(), AsyncMock()
    monkeypatch.setattr(main.local_users, "init_db", Mock())
    monkeypatch.setattr(main.litellm, "start_client", started)
    monkeypatch.setattr(main.litellm, "close_client", closed)
    mapping = load_mapping({}, "")
    monkeypatch.setattr(main, "get_mapping", Mock(return_value=mapping))
    provision = AsyncMock()
    monkeypatch.setattr(main.organization_provisioning, "provision_members", provision)
    return started, closed, provision


@pytest.mark.asyncio
async def test_startup_provisions_before_serving_and_closes_pool(lifecycle):
    started, closed, provision = lifecycle
    async with main.lifespan(main.app):
        started.assert_awaited_once()
        provision.assert_awaited_once()
        closed.assert_not_awaited()
    closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_provisioning_closes_pool_and_never_serves(lifecycle):
    _, closed, provision = lifecycle
    provision.side_effect = RuntimeError("provisioning unavailable")
    with pytest.raises(RuntimeError, match="provisioning unavailable"):
        async with main.lifespan(main.app):
            pytest.fail("Startup failure must prevent serving")
    closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_mapping_closes_pool(lifecycle):
    _, closed, _ = lifecycle
    main.get_mapping.side_effect = ValueError("invalid mapping")
    with pytest.raises(ValueError, match="invalid mapping"):
        async with main.lifespan(main.app):
            pytest.fail("Invalid mapping must prevent serving")
    closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_hierarchy_reconciliation_keeps_its_lifecycle(lifecycle, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    _, closed, _ = lifecycle
    monkeypatch.setattr(settings, "organization_hierarchy", SimpleNamespace(levels=["root"]))
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def reconcile():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(main.organization_sync, "run_reconciliation", reconcile)
    async with main.lifespan(main.app):
        await entered.wait()
    assert cancelled.is_set()
    closed.assert_awaited_once()
