import asyncio
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
import jwt

from app.config import settings
from app.dependencies import get_current_user
from app.models import CurrentUser
from app.services import litellm as llm
from app.services import local_users
from app.services import oidc as oidc_svc

router = APIRouter(prefix="/auth", tags=["auth"])


def _make_jwt(
    user_id: str,
    email: str,
    role: str = "user",
    auth_source: str = "sso",
    team_ids: list[str] | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "role": role,
            "auth_source": auth_source,
            "team_ids": team_ids or [],
            "exp": expire,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@router.get("/login")
async def login():
    if not settings.oidc_issuer_url:
        raise HTTPException(status_code=503, detail="SSO not configured")
    state = oidc_svc.generate_state()
    return RedirectResponse(await oidc_svc.get_authorization_url(state))


@router.get("/callback")
async def callback(code: str = Query(...), state: str = Query(...)):
    if not oidc_svc.validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid state")
    tokens = await oidc_svc.exchange_code(code)
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="No id_token in response")
    claims = await oidc_svc.verify_id_token(id_token)
    user_id, email = claims["sub"], claims.get("email", "")
    role = "admin" if settings.is_admin_identity(email, claims) else "user"
    team_ids = settings.mapped_team_ids(claims)
    if settings.oidc_require_team_mapping and not team_ids:
        raise HTTPException(status_code=403, detail="Your SSO groups are not mapped to a LiteLLM team")

    provisioned_user = await llm.ensure_user_exists(user_id, email)
    if provisioned_user is None and (
        settings.oidc_group_team_mapping or settings.oidc_require_team_mapping
    ):
        raise HTTPException(status_code=502, detail="Could not provision the LiteLLM user")
    if team_ids:
        await llm.sync_user_team_memberships(user_id, email, team_ids)

    token = _make_jwt(user_id, email, role, "sso", team_ids)
    # A URL fragment is not sent to nginx or stored in server access logs.
    return RedirectResponse(f"{settings.root_url}/auth/callback#token={token}")


@router.post("/local")
async def local_login(username: str = Form(...), password: str = Form(...)):
    """Authenticate the bootstrap admin or an admin-created local account."""
    bootstrap_match = bool(
        settings.local_auth_enabled
        and hmac.compare_digest(username, settings.local_auth_username or "")
        and hmac.compare_digest(password, settings.local_auth_password or "")
    )
    if bootstrap_match:
        user_id = f"local:{username.lower()}"
        email = f"{username}@local"
        role = "admin"
    elif settings.local_users_enabled:
        account = await asyncio.to_thread(local_users.authenticate, username, password)
        if not account:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user_id = account["user_id"]
        email = account["email"]
        role = account["role"]
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    await llm.ensure_user_exists(user_id, email)
    return JSONResponse(
        {"token": _make_jwt(user_id, email, role, "local")},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/config")
async def auth_config():
    return {
        "sso_enabled": bool(settings.oidc_issuer_url),
        "local_enabled": settings.local_auth_enabled or settings.local_users_enabled,
    }


@router.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user
