"""Opt-in real subject keyless creation contract for pinned LiteLLM."""

import os
from uuid import uuid4
import pytest
from app.services import litellm
from app.services import litellm_identity as remote

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LITELLM_INTEGRATION") != "1", reason="requires the opt-in pinned LiteLLM integration stack")


@pytest.mark.asyncio
async def test_actual_subject_created_without_key():
    suffix = uuid4().hex[:12]
    subject = f"sso-integration-{suffix}"
    email = f"identity-{suffix}@example.invalid"
    await litellm.ensure_user_exists(subject, email)
    assert (await remote.get_user(subject))["user_email"] == email
    assert (await litellm.get_user(subject))["keys"] == []
    # Keep the synthetic row in the disposable integration database.
