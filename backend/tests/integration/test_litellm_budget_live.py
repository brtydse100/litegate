"""Pinned native-budget evidence; this fixture is deliberately not strict mode.

Run against the dedicated 1.109.1 mock-provider Compose fixture with
RUN_LITELLM_BUDGET_INTEGRATION=1. This records native management/read-time
contracts and the default request-cost overshoot that blocks activation.
"""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest

from app.config import settings
from app.services import budget_native, organization_client as upstream
from app.services.litellm_client import headers

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_BUDGET_INTEGRATION") != "1",
    reason="requires the dedicated pinned LiteLLM budget integration fixture",
)


@pytest.mark.asyncio
async def test_native_zero_and_parallel_multi_key_budget_contract():
    suffix = uuid4().hex[:12]
    user, team = f"budget-{suffix}", f"budget-team-{suffix}"
    keys, created_team, created_user = [], False, False
    try:
        await upstream.request("POST", "/user/new", payload={"user_id": user, "user_email": f"{user}@example.invalid"})
        created_user = True
        await upstream.request("POST", "/team/new", payload={"team_id": team, "max_budget": 10, "budget_duration": "1h"})
        created_team = True
        await upstream.request(
            "POST",
            "/team/member_add",
            payload={"team_id": team, "member": {"role": "user", "user_id": user}, "max_budget_in_team": 0, "budget_duration": "1h"},
        )
        for _ in range(2):
            generated = await upstream.request("POST", "/key/generate", payload={"user_id": user, "team_id": team})
            keys.append(generated["key"])
        before = upstream.membership(await upstream.team_info(team), user)
        assert before["litellm_budget_table"]["max_budget"] == 0
        reset_at = before["litellm_budget_table"]["budget_reset_at"]
        assert reset_at
        async with httpx.AsyncClient(base_url=settings.litellm_url, timeout=30) as client:

            async def infer(key):
                return await client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": "litegate-integration-mock", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 10},
                )

            zero = await asyncio.gather(*(infer(key) for key in keys))
            assert all(response.status_code == 422 and response.json()["error"]["type"] == "budget_exceeded" for response in zero)
            await budget_native.write_amount({"team_id": team, "user_id": user, "amount": 1})
            assert await budget_native.read_amount({"team_id": team, "user_id": user}) == 1
            after = upstream.membership(await upstream.team_info(team), user)
            assert after["spend"] == before["spend"]
            assert after["litellm_budget_table"]["budget_reset_at"] == reset_at
            results = await asyncio.gather(*(infer(key) for key in keys))
            # Default upstream reservations admit one request whose cost exceeds
            # the entire $0.000001 allowance; the other key shares the same cap.
            assert sorted(response.status_code for response in results) == [200, 422]
            denied = next(response for response in results if response.status_code == 422)
            assert denied.json()["error"]["type"] == "budget_exceeded"
        capability = await budget_native.capabilities()
        assert capability["supported"] is False
    finally:
        if keys:
            await upstream.request("POST", "/key/delete", payload={"keys": keys})
        if created_team:
            await upstream.request("POST", "/team/delete", payload={"team_ids": [team]})
        if created_user:
            # User deletion returns a list, unlike organization object contracts.
            async with httpx.AsyncClient(base_url=settings.litellm_url, headers=headers(), timeout=30) as client:
                response = await client.post("/user/delete", json={"user_ids": [user]})
                response.raise_for_status()
