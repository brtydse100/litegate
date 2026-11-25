"""People cannot mint keys around LiteGate on the pinned LiteLLM, and LiteGate still can."""

import os
from uuid import uuid4

import httpx
import pytest

from app.config import settings
from app.services import litellm, litellm_roles

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LITELLM_INTEGRATION") != "1", reason="requires the opt-in LiteLLM integration stack")


def own(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def attempts(key: str) -> dict:
    async with httpx.AsyncClient(base_url=settings.litellm_url, timeout=30) as client:
        personal = await client.post("/key/generate", headers=own(key), json={})
        widen = await client.post("/key/update", headers=own(key), json={"key": key, "max_budget": None})
        chat = await client.post(
            "/chat/completions",
            headers=own(key),
            json={"model": "litegate-integration-mock", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 10},
        )
    return {"personal": personal.status_code, "widen": widen.status_code, "chat": chat.status_code}


@pytest.mark.asyncio
async def test_new_person_is_a_viewer_whose_key_cannot_mint_keys():
    user_id = f"lockdown-new-{uuid4().hex[:12]}"
    await litellm.ensure_user_exists(user_id, f"{user_id}@example.invalid")
    assert litellm_roles.role_of(await litellm.get_user(user_id)) == "internal_user_viewer"
    key = (await litellm.generate_key(user_id, f"{user_id}@example.invalid", initial_spend=0))["key"]

    result = await attempts(key)

    assert result["personal"] in (400, 401, 403)
    assert result["widen"] in (400, 401, 403)
    assert result["chat"] == 200


@pytest.mark.asyncio
async def test_existing_self_service_person_is_switched_at_sign_in():
    user_id = f"lockdown-old-{uuid4().hex[:12]}"
    async with httpx.AsyncClient(base_url=settings.litellm_url, timeout=30) as client:
        created = await client.post(
            "/user/new",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={"user_id": user_id, "user_email": f"{user_id}@example.invalid", "auto_create_key": False},
        )
    created.raise_for_status()
    key = (await litellm.generate_key(user_id, f"{user_id}@example.invalid"))["key"]

    await litellm.ensure_user_exists(user_id, f"{user_id}@example.invalid")

    assert litellm_roles.role_of(await litellm.get_user(user_id)) == "internal_user_viewer"
    result = await attempts(key)
    assert result["personal"] in (400, 401, 403)
    assert result["chat"] == 200


@pytest.mark.asyncio
async def test_lockdown_setting_blocks_self_service_role_too():
    """The documented key_generation_settings also stop people LiteGate never switched."""
    user_id = f"lockdown-raw-{uuid4().hex[:12]}"
    async with httpx.AsyncClient(base_url=settings.litellm_url, timeout=30) as client:
        created = await client.post(
            "/user/new",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={"user_id": user_id, "user_email": f"{user_id}@example.invalid", "auto_create_key": False},
        )
    created.raise_for_status()
    key = (await litellm.generate_key(user_id, f"{user_id}@example.invalid"))["key"]

    result = await attempts(key)

    assert result["personal"] in (400, 401, 403)
    assert result["chat"] == 200
