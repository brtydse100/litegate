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
_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0.0
_DISCOVERY_TTL = 3600.0  # re-fetch OIDC config at most once per hour
_signer = None
_signer_secret: Optional[str] = None


def _get_signer() -> URLSafeTimedSerializer:
    global _signer, _signer_secret
    if _signer is None or _signer_secret != settings.jwt_secret:
        _signer = URLSafeTimedSerializer(settings.jwt_secret)
        _signer_secret = settings.jwt_secret
    return _signer


def _load_state(state: str) -> dict:
    last_error: BadSignature | SignatureExpired | None = None
    for secret in settings.jwt_verification_secrets:
        signer = _get_signer() if secret == settings.jwt_secret else URLSafeTimedSerializer(secret)
        try:
            payload = signer.loads(state, max_age=600)
            return payload if isinstance(payload, dict) else {}
        except (BadSignature, SignatureExpired) as exc:
            last_error = exc
    raise last_error or BadSignature("No state verification secret configured")


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
        _load_state(state)
        return True
    except (BadSignature, SignatureExpired):
        return False


def state_nonce(state: str) -> str:
    try:
        payload = _load_state(state)
        nonce = payload.get("nonce", "")
        return nonce if isinstance(nonce, str) else ""
    except (BadSignature, SignatureExpired):
        return ""


async def get_authorization_url(state: str) -> str:
    discovery = await get_discovery()
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
        "nonce": state_nonce(state),
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


async def get_jwks(force_refresh: bool = False) -> dict:
    global _jwks_cache, _jwks_cache_time
    now = time.monotonic()
    if not force_refresh and _jwks_cache is not None and now - _jwks_cache_time < _DISCOVERY_TTL:
        return _jwks_cache
    discovery = await get_discovery()
    async with httpx.AsyncClient() as client:
        r = await client.get(discovery["jwks_uri"], timeout=10)
        r.raise_for_status()
        _jwks_cache = r.json()
        _jwks_cache_time = now
        return _jwks_cache


async def verify_id_token(id_token: str, expected_nonce: str = "") -> dict:
    jwks = await get_jwks()
    discovery = await get_discovery()

    # Match the token's kid to a single verified JWK.
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    keys = jwks.get("keys", [jwks])
    if not isinstance(keys, list) or not keys or not all(isinstance(key, dict) for key in keys):
        raise jwt.InvalidTokenError("OIDC provider returned no usable signing keys")
    if kid:
        key = next((key for key in keys if key.get("kid") == kid), None)
        if key is None:
            # Providers rotate keys. Retry once without the cache before rejecting
            # a token whose key ID is not present in the cached key set.
            refreshed = await get_jwks(force_refresh=True)
            refreshed_keys = refreshed.get("keys", [refreshed])
            key = next(
                (candidate for candidate in refreshed_keys if isinstance(candidate, dict) and candidate.get("kid") == kid),
                None,
            )
            if key is None:
                raise jwt.InvalidTokenError("OIDC signing key not found")
    elif len(keys) == 1:
        key = keys[0]
    else:
        raise jwt.InvalidTokenError("OIDC token did not identify a signing key")

    claims = jwt.decode(
        id_token,
        jwt.PyJWK.from_dict(key),
        algorithms=["RS256"],
        audience=settings.oidc_client_id,
        issuer=discovery.get("issuer", settings.oidc_issuer_url),
        options={"verify_exp": True},
    )
    if expected_nonce and not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise jwt.InvalidTokenError("OIDC nonce mismatch")
    return claims
