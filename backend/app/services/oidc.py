import httpx
import secrets
import json
import base64
import time
from typing import Optional
from urllib.parse import urlencode
import jwt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import settings

_discovery_cache: Optional[dict] = None
_discovery_cache_time: float = 0.0
_DISCOVERY_TTL = 3600.0  # re-fetch OIDC config at most once per hour
_signer = None


def _get_signer() -> URLSafeTimedSerializer:
    global _signer
    if _signer is None:
        _signer = URLSafeTimedSerializer(settings.jwt_secret)
    return _signer


async def get_discovery() -> dict:
    global _discovery_cache, _discovery_cache_time
    now = time.monotonic()
    if _discovery_cache is not None and now - _discovery_cache_time < _DISCOVERY_TTL:
        return _discovery_cache
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.oidc_issuer_url}/.well-known/openid-configuration",
            timeout=10,
        )
        r.raise_for_status()
        _discovery_cache = r.json()
        _discovery_cache_time = now
    return _discovery_cache


def generate_state() -> str:
    return _get_signer().dumps({"nonce": secrets.token_urlsafe(16)})


def validate_state(state: str) -> bool:
    try:
        _get_signer().loads(state, max_age=600)
        return True
    except (BadSignature, SignatureExpired):
        return False


async def get_authorization_url(state: str) -> str:
    discovery = await get_discovery()
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
    }
    return f"{discovery['authorization_endpoint']}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    discovery = await get_discovery()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()


async def get_jwks() -> dict:
    discovery = await get_discovery()
    async with httpx.AsyncClient() as client:
        r = await client.get(discovery["jwks_uri"], timeout=10)
        r.raise_for_status()
        return r.json()


async def verify_id_token(id_token: str) -> dict:
    jwks = await get_jwks()
    discovery = await get_discovery()

    # Match the token's kid to a single verified JWK.
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    keys = jwks.get("keys", [jwks])
    key = next((k for k in keys if k.get("kid") == kid), None) if kid else None
    if key is None:
        key = keys[0]

    return jwt.decode(
        id_token,
        jwt.PyJWK.from_dict(key),
        algorithms=["RS256"],
        audience=settings.oidc_client_id,
        issuer=discovery.get("issuer", settings.oidc_issuer_url),
        options={"verify_exp": True},
    )
