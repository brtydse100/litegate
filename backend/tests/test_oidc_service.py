import json
import time

import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response
from itsdangerous import URLSafeTimedSerializer
from jwt.algorithms import RSAAlgorithm

from app.services import oidc


def test_oidc_flow_started_before_secret_rotation_can_finish(monkeypatch):
    old_secret = "old-session-secret-that-is-long-enough"
    monkeypatch.setattr(oidc.settings, "jwt_secret", "new-session-secret-that-is-long-enough")
    monkeypatch.setattr(oidc.settings, "jwt_previous_secrets", old_secret)
    state = URLSafeTimedSerializer(old_secret).dumps({"nonce": "rotation-nonce"})

    assert oidc.validate_state(state) is True
    assert oidc.state_nonce(state) == "rotation-nonce"


def _signed_id_token(*, kid: str, nonce: str) -> tuple[str, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = kid
    token = jwt.encode(
        {
            "sub": "oidc-user",
            "iss": "https://idp.example",
            "aud": "litegate-client",
            "exp": int(time.time()) + 300,
            "nonce": nonce,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    return token, public_jwk


@pytest.mark.asyncio
async def test_id_token_verification_refreshes_rotated_signing_keys(monkeypatch):
    token, rotated_key = _signed_id_token(kid="rotated-key", nonce="browser-nonce")
    refreshes: list[bool] = []

    async def jwks(force_refresh: bool = False):
        refreshes.append(force_refresh)
        return {"keys": [rotated_key] if force_refresh else [{"kid": "old-key"}]}

    async def discovery():
        return {"issuer": "https://idp.example"}

    monkeypatch.setattr(oidc.settings, "oidc_client_id", "litegate-client")
    monkeypatch.setattr(oidc, "get_jwks", jwks)
    monkeypatch.setattr(oidc, "get_discovery", discovery)

    claims = await oidc.verify_id_token(token, expected_nonce="browser-nonce")

    assert claims["sub"] == "oidc-user"
    assert refreshes == [False, True]


@pytest.mark.asyncio
async def test_id_token_verification_rejects_a_nonce_from_another_login(monkeypatch):
    token, signing_key = _signed_id_token(kid="current-key", nonce="first-browser")

    async def jwks(force_refresh: bool = False):
        return {"keys": [signing_key]}

    async def discovery():
        return {"issuer": "https://idp.example"}

    monkeypatch.setattr(oidc.settings, "oidc_client_id", "litegate-client")
    monkeypatch.setattr(oidc, "get_jwks", jwks)
    monkeypatch.setattr(oidc, "get_discovery", discovery)

    with pytest.raises(jwt.InvalidTokenError, match="nonce mismatch"):
        await oidc.verify_id_token(token, expected_nonce="second-browser")


@pytest.mark.asyncio
@respx.mock
async def test_manual_oidc_endpoints_skip_discovery(monkeypatch):
    id_token, signing_key = _signed_id_token(kid="manual-key", nonce="manual-nonce")
    monkeypatch.setattr(oidc.settings, "oidc_issuer_url", "https://idp.example")
    monkeypatch.setattr(oidc.settings, "oidc_client_id", "litegate-client")
    monkeypatch.setattr(oidc.settings, "oidc_redirect_uri", "https://litegate.example/callback")
    monkeypatch.setattr(oidc.settings, "oidc_authorization_endpoint", "https://idp.example/authorize")
    monkeypatch.setattr(oidc.settings, "oidc_token_endpoint", "https://idp.example/token")
    monkeypatch.setattr(oidc.settings, "oidc_jwks_uri", "https://idp.example/keys")
    monkeypatch.setattr(oidc, "_jwks_cache", None)
    discovery = respx.get("https://idp.example/.well-known/openid-configuration")
    token = respx.post("https://idp.example/token").mock(return_value=Response(200, json={"id_token": id_token}))
    keys = respx.get("https://idp.example/keys").mock(return_value=Response(200, json={"keys": [signing_key]}))

    state = oidc.generate_state()
    authorization_url = await oidc.get_authorization_url(state)
    exchanged = await oidc.exchange_code("code")
    claims = await oidc.verify_id_token(exchanged["id_token"], expected_nonce="manual-nonce")

    assert authorization_url.startswith("https://idp.example/authorize?")
    assert claims["sub"] == "oidc-user"
    assert discovery.called is False
    assert token.calls.last.request.content
    assert keys.called is True


@pytest.mark.asyncio
@respx.mock
async def test_discovery_remains_the_default(monkeypatch):
    monkeypatch.setattr(oidc.settings, "oidc_issuer_url", "https://discovery.example")
    monkeypatch.setattr(oidc.settings, "oidc_authorization_endpoint", "")
    monkeypatch.setattr(oidc.settings, "oidc_token_endpoint", "")
    monkeypatch.setattr(oidc.settings, "oidc_jwks_uri", "")
    monkeypatch.setattr(oidc, "_discovery_cache", None)
    discovery = respx.get("https://discovery.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "issuer": "https://discovery.example",
                "authorization_endpoint": "https://discovery.example/authorize",
                "token_endpoint": "https://discovery.example/token",
                "jwks_uri": "https://discovery.example/keys",
            },
        )
    )

    metadata = await oidc.get_provider_metadata()

    assert metadata["jwks_uri"] == "https://discovery.example/keys"
    assert discovery.called is True
