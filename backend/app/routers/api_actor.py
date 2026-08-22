"""Authentication and audit context shared by the stable management routers."""

import asyncio
import hmac
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi import Cookie
from fastapi.security import HTTPAuthorizationCredentials
from jwt import InvalidTokenError

from app.config import settings
from app.dependencies import bearer, decode_portal_token, enforce_account_state
from app.models import CurrentUser
from app.services import audit, litellm as llm


@dataclass
class ApiActor:
    user: CurrentUser
    proof_key: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.user.is_admin


async def get_api_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    session_cookie: Optional[str] = Cookie(default=None, alias="litegate_session"),
) -> ApiActor:
    if x_api_key and settings.management_api_key and hmac.compare_digest(x_api_key, settings.management_api_key):
        return ApiActor(CurrentUser(user_id="api:management", email="management-api@local", role="admin", auth_source="management_api_key"))
    if credentials:
        token = credentials.credentials
        try:
            return ApiActor(enforce_account_state(decode_portal_token(token)))
        except InvalidTokenError:
            info = await llm.get_key_info(token)
            if info is not None:
                return ApiActor(CurrentUser(user_id=info.get("user_id") or "key-holder", email="", role="user", auth_source="litellm_key"), proof_key=token)
    if session_cookie:
        try:
            return ApiActor(enforce_account_state(decode_portal_token(session_cookie)))
        except InvalidTokenError:
            pass
    raise HTTPException(status_code=401, detail="Valid portal token, management key, or LiteLLM key required")


def require_api_admin(actor: ApiActor) -> None:
    if not actor.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")


async def record_audit(actor: ApiActor, action: str, target: str, *, outcome: str = "success", details: Optional[dict] = None) -> None:
    await asyncio.to_thread(audit.record, actor_id=actor.user.user_id, actor_email=actor.user.email, action=action, target=target, outcome=outcome, details=details)
