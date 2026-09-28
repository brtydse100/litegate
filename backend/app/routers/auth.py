import asyncio
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
import jwt

from app.config import settings
from app.dependencies import get_current_user
from app.models import CurrentUser
from app.rate_limit import check_login_rate_limit, clear_login_failures, record_login_failure
from app.services import litellm as llm
from app.services import local_users
from app.services import oidc as oidc_svc

router = APIRouter(prefix="/auth", tags=["auth"])
_OIDC_STATE_COOKIE = "litegate_oidc_state"
_SESSION_COOKIE = "litegate_session"


def _login_client_id(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    if host in {"127.0.0.1", "::1"}:
        forwarded = request.headers.get("x-real-ip", "").strip()
        if forwarded:
            host = forwarded
    return host[:128]


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


def _set_session_cookie(response: JSONResponse | RedirectResponse, token: str) -> None:
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        secure=settings.root_url.casefold().startswith("https://"),
        samesite="lax",
        path="/api",
    )


def _is_litellm_proxy_admin(user: dict | None) -> bool:
    if not isinstance(user, dict):
        return False
    details = user.get("user_info", user)
    return isinstance(details, dict) and details.get("user_role") == "proxy_admin"


@router.get("/login")
async def login():
    if not settings.oidc_issuer_url:
        raise HTTPException(status_code=503, detail="SSO not configured")
    state = oidc_svc.generate_state()
    response = RedirectResponse(await oidc_svc.get_authorization_url(state))
    response.set_cookie(
        _OIDC_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.root_url.casefold().startswith("https://"),
        samesite="lax",
        path="/api/auth",
    )
    return response


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    state_cookie: str | None = Cookie(default=None, alias=_OIDC_STATE_COOKIE),
):
    if not state_cookie or not hmac.compare_digest(state, state_cookie) or not oidc_svc.validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid state")
    nonce = oidc_svc.state_nonce(state)
    if not nonce:
        raise HTTPException(status_code=400, detail="Invalid state")
    tokens = await oidc_svc.exchange_code(code)
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="No id_token in response")
    claims = await oidc_svc.verify_id_token(id_token, expected_nonce=nonce)
    user_id, email = claims["sub"], claims.get("email", "")
    group_team_ids = settings.mapped_team_ids(claims)
    if settings.oidc_require_team_mapping and not group_team_ids:
        raise HTTPException(status_code=403, detail="Your SSO groups are not mapped to a LiteLLM team")
    team_ids = list(group_team_ids)
    default_team_id = settings.sso_default_team_id.strip()
    if default_team_id and default_team_id not in team_ids:
        team_ids.append(default_team_id)

    provisioned_user = await llm.ensure_user_exists(user_id, email)
    if provisioned_user is None and (team_ids or settings.oidc_require_team_mapping or settings.inherit_litellm_admin):
        raise HTTPException(status_code=502, detail="Could not provision the LiteLLM user")
    if team_ids:
        await llm.sync_user_team_memberships(user_id, email, team_ids)

    role = "admin" if settings.is_admin_identity(email, claims) else "user"
    if settings.inherit_litellm_admin and _is_litellm_proxy_admin(provisioned_user):
        role = "admin"

    token = _make_jwt(user_id, email, role, "sso", team_ids)
    response = RedirectResponse(f"{settings.root_url}/auth/callback")
    _set_session_cookie(response, token)
    response.delete_cookie(_OIDC_STATE_COOKIE, path="/api/auth")
    return response


@router.post("/local")
async def local_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Authenticate the bootstrap admin or an admin-created local account."""
    client_id = _login_client_id(request)
    check_login_rate_limit(client_id)
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
            record_login_failure(client_id)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user_id = account["user_id"]
        email = account["email"]
        role = account["role"]
    else:
        record_login_failure(client_id)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    clear_login_failures(client_id)
    await llm.ensure_user_exists(user_id, email)
    response = JSONResponse({"authenticated": True}, headers={"Cache-Control": "no-store"})
    _set_session_cookie(response, _make_jwt(user_id, email, role, "local"))
    return response


@router.post("/logout")
async def logout():
    response = JSONResponse({"signed_out": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(_SESSION_COOKIE, path="/api")
    return response


@router.get("/config")
async def auth_config():
    return {
        "sso_enabled": bool(settings.oidc_issuer_url),
        "local_enabled": settings.local_auth_enabled or settings.local_users_enabled,
    }


@router.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user
