from fastapi import Depends, HTTPException, status
from fastapi import Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import InvalidTokenError
from app.config import settings
from app.models import CurrentUser
from app.services import local_users

bearer = HTTPBearer(auto_error=False)
_SESSION_COOKIE = "litegate_session"


def decode_portal_token(token: str) -> CurrentUser:
    last_error: InvalidTokenError | None = None
    payload = None
    for secret in settings.jwt_verification_secrets:
        try:
            payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
            break
        except InvalidTokenError as exc:
            last_error = exc
    if payload is None:
        raise last_error or InvalidTokenError("No session verification secret configured")
    user_id: str = payload.get("sub")
    email: str = payload.get("email", "")
    if not user_id:
        raise InvalidTokenError("Missing subject")
    return CurrentUser(
        user_id=user_id,
        email=email,
        role=payload.get("role", "user"),
        auth_source=payload.get("auth_source", "sso"),
        team_ids=payload.get("team_ids", []),
    )


def enforce_account_state(current_user: CurrentUser) -> CurrentUser:
    """Refresh local role/active state so disabling an account revokes sessions immediately."""
    if current_user.auth_source != "local":
        return current_user
    username = current_user.user_id.removeprefix("local:")
    is_bootstrap = bool(
        settings.local_auth_enabled
        and username.lower() == (settings.local_auth_username or "").lower()
    )
    if is_bootstrap:
        current_user.role = "admin"
        return current_user
    account = local_users.get_user(username)
    if not account or not account["active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
    current_user.email = account["email"]
    current_user.role = account["role"]
    return current_user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session_cookie: str | None = Cookie(default=None, alias=_SESSION_COOKIE),
) -> CurrentUser:
    token = credentials.credentials if credentials is not None else session_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        return enforce_account_state(decode_portal_token(token))
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return current_user
