"""Verify TLS policy reaches every outbound LiteLLM and SSO HTTP client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import generic_sso, litellm_client, oidc


@pytest.mark.asyncio
@pytest.mark.parametrize("verify", [True, False])
async def test_oidc_discovery_token_and_jwks_use_tls_policy(monkeypatch, verify):
    monkeypatch.setattr(oidc.settings, "ssl_verify", verify)
    monkeypatch.setattr(oidc.settings, "oidc_issuer_url", "https://idp.example")
    monkeypatch.setattr(oidc.settings, "oidc_authorization_endpoint", "")
    monkeypatch.setattr(oidc, "_discovery_cache", None)
    monkeypatch.setattr(oidc, "_jwks_cache", None)
    clients = []
    requests = []
    original = httpx.AsyncClient

    def handle(request):
        requests.append(request.url.path)
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"token_endpoint": "https://idp.example/token", "jwks_uri": "https://idp.example/keys"})
        if request.url.path == "/token":
            return httpx.Response(200, json={"id_token": "test-token"})
        return httpx.Response(200, json={"keys": []})

    def client(**kwargs):
        clients.append(kwargs)
        return original(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(oidc.httpx, "AsyncClient", client)
    await oidc.get_discovery()
    await oidc.exchange_code("code")
    await oidc.get_jwks()
    assert requests == ["/.well-known/openid-configuration", "/token", "/keys"]
    assert [kwargs["verify"] for kwargs in clients] == [verify] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize("verify", [True, False])
async def test_generic_token_and_userinfo_use_tls_policy(monkeypatch, verify):
    monkeypatch.setattr(generic_sso.settings, "ssl_verify", verify)
    monkeypatch.setattr(generic_sso.settings, "generic_token_endpoint", "https://idp.example/token")
    monkeypatch.setattr(generic_sso.settings, "generic_userinfo_endpoint", "https://idp.example/userinfo")
    monkeypatch.setattr(generic_sso.settings, "generic_user_id_attribute", "sub")
    monkeypatch.setattr(generic_sso.settings, "generic_user_email_attribute", "email")
    monkeypatch.setattr(generic_sso.settings, "generic_client_use_pkce", False)
    requests = []
    original = httpx.AsyncClient

    def handle(request):
        requests.append(request.url.path)
        payload = {"access_token": "test-token"} if request.url.path == "/token" else {"sub": "user"}
        return httpx.Response(200, json=payload)

    with patch.object(
        generic_sso.httpx, "AsyncClient", side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    ) as client:
        claims = await generic_sso.get_user_claims("code", "state")
    assert claims["sub"] == "user"
    assert requests == ["/token", "/userinfo"]
    client.assert_called_once_with(follow_redirects=False, verify=verify)


@pytest.mark.asyncio
@pytest.mark.parametrize("verify", [True, False])
async def test_litellm_pool_and_fallback_use_tls_policy(monkeypatch, verify):
    monkeypatch.setattr(litellm_client.settings, "ssl_verify", verify)
    monkeypatch.setattr(litellm_client, "_shared_client", None)
    with patch.object(litellm_client.httpx, "AsyncClient") as client:
        client.return_value.aclose = AsyncMock()
        await litellm_client.start_client()
        try:
            assert client.call_args.kwargs["verify"] is verify
            async with litellm_client.client() as pooled:
                assert pooled is client.return_value
            assert client.call_count == 1
        finally:
            await litellm_client.close_client()
        async with litellm_client.client():
            pass
        assert client.call_count == 2
        assert client.call_args.kwargs["verify"] is verify
