"""Generic OAuth SSO using the provider's authenticated UserInfo endpoint."""

import base64
import hashlib
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services import oidc


def get_authorization_url(state: str) -> str:
    endpoint = urlsplit(settings.generic_authorization_endpoint)
    params = dict(parse_qsl(endpoint.query, keep_blank_values=True))
    params.update(
        response_type="code",
        client_id=settings.generic_client_id,
        redirect_uri=settings.generic_callback_uri,
        scope=settings.generic_scope,
        state=state,
    )
    if settings.generic_client_use_pkce:
        digest = hashlib.sha256(oidc.state_pkce_verifier(state).encode()).digest()
        params.update(code_challenge=base64.urlsafe_b64encode(digest).rstrip(b"=").decode(), code_challenge_method="S256")
    return urlunsplit(endpoint._replace(query=urlencode(params)))


def _attribute(userinfo: dict, path: str) -> object:
    value: object = userinfo
    for segment in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


async def get_user_claims(code: str, state: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.generic_callback_uri,
    }
    if settings.generic_include_client_id:
        data.update(client_id=settings.generic_client_id, client_secret=settings.generic_client_secret)
        auth = None
    else:
        auth = httpx.BasicAuth(quote_plus(settings.generic_client_id, safe=""), quote_plus(settings.generic_client_secret, safe=""))
    if settings.generic_client_use_pkce:
        data["code_verifier"] = oidc.state_pkce_verifier(state)

    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.post(settings.generic_token_endpoint, data=data, auth=auth, timeout=10)
            response.raise_for_status()
            tokens = response.json()
            access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
            if not isinstance(access_token, str) or not access_token.strip():
                raise HTTPException(status_code=502, detail="SSO provider returned no usable access token")
            token_type = tokens.get("token_type", "Bearer")
            if not isinstance(token_type, str) or token_type.casefold() != "bearer":
                raise HTTPException(status_code=502, detail="SSO provider returned an unsupported token type")
            response = await client.get(
                settings.generic_userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            response.raise_for_status()
            userinfo = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not authenticate with the SSO provider") from exc

    if not isinstance(userinfo, dict):
        raise HTTPException(status_code=502, detail="SSO provider returned invalid UserInfo")
    user_id = _attribute(userinfo, settings.generic_user_id_attribute)
    email = _attribute(userinfo, settings.generic_user_email_attribute)
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=502, detail="SSO UserInfo is missing a usable user ID")
    if email is not None and (not isinstance(email, str) or not email.strip()):
        raise HTTPException(status_code=502, detail="SSO UserInfo contains an invalid email")
    if userinfo.get("email_verified") is False and email:
        raise HTTPException(status_code=403, detail="SSO provider has not verified the email address")
    return {**userinfo, "sub": user_id, "email": email or ""}
