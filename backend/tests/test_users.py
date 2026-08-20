from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models import CurrentUser, LocalUserCreate, LocalUserUpdate
from app.rate_limit import _key_ops, check_key_rate_limit, key_rate_limit_status
from app.routers.users import create_local_user, update_local_user


def setup_function():
    _key_ops.clear()


@pytest.mark.asyncio
async def test_create_local_user_consumes_admin_operation_allowance():
    admin = CurrentUser(user_id="local:admin", email="admin@local", role="admin")
    payload = LocalUserCreate(
        username="contractor",
        email="contractor@example.com",
        password="long-password",
        role="user",
    )
    created = {
        "username": "contractor",
        "user_id": "local:contractor",
        "email": "contractor@example.com",
        "role": "user",
        "active": True,
    }
    with (
        patch("app.routers.users.local_users.create_user", return_value=created),
        patch("app.routers.users.llm.ensure_user_exists", new=AsyncMock()),
    ):
        result = await create_local_user(payload, admin)

    assert result == created
    assert key_rate_limit_status(admin.user_id)["remaining"] == 4


@pytest.mark.asyncio
async def test_update_local_user_stops_after_operation_limit():
    admin = CurrentUser(user_id="local:admin", email="admin@local", role="admin")
    for _ in range(5):
        check_key_rate_limit(admin.user_id)

    with pytest.raises(HTTPException) as exc:
        await update_local_user(
            "contractor",
            LocalUserUpdate(active=False),
            admin,
        )

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"
