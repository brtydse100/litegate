import base64
import hashlib
from urllib.parse import parse_qs, unquote_plus, urlsplit
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer

from app.routers import auth
from app.services import generic_sso, oidc


@pytest.fixture
def provider(monkeypatch):
    configured = auth.settings
    monkeypatch.setattr(generic_sso, "settings", configured)
    monkeypatch.setattr(oidc, "settings", configured)
    for field, value in {
        "oidc_issuer_url": "",
        "generic_client_id": "generic-client",
        "generic_client_secret": "test-provider-secret",
        "generic_authorization_endpoint": "https://idp.example/authorize?audience=portal",
        "generic_token_endpoint": "https://idp.example/token",
        "generic_userinfo_endpoint": "https://idp.example/userinfo",
        "generic_redirect_uri": "",
        "root_url": "https://portal.example",
        "generic_user_id_attribute": "identity.employee_id",
        "generic_user_email_attribute": "mail",
        "generic_client_use_pkce": True,
        "generic_include_client_id": True,
        "generic_require_verified_email": True,
        "admin_emails": "",
        "admin_groups": "",
        "oidc_groups_claim": "groups",
        "oidc_group_team_mapping": {},
        "oidc_require_team_mapping": False,
        "sso_default_team_id": "",
        "inherit_litellm_admin": False,
    }.items():
        monkeypatch.setattr(configured, field, value)
    return configured


def mock_provider(monkeypatch, *, token=None, userinfo=None, status=200):
    requests = []
    token = {"access_token": "opaque-provider-token", "token_type": "Bearer"} if token is None else token
    userinfo = {"identity": {"employee_id": "employee-123"}, "mail": "alex@example.com", "groups": ["Engineering"]} if userinfo is None else userinfo

    def handle(request):
        requests.append(request)
        payload = token if request.url.path == "/token" else userinfo
        return httpx.Response(status, json=payload)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        generic_sso.httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs) if "transport" in kwargs else original(transport=httpx.MockTransport(handle), **kwargs),
    )
    return requests


@pytest.mark.asyncio
async def test_generic_login_and_callback_use_opaque_token_userinfo_and_secure_session(provider, monkeypatch):
    provider.admin_groups = "Engineering"
    provider.oidc_group_team_mapping = {"Engineering": "team-engineering"}
    ensure = AsyncMock(return_value={"user_id": "employee-123"})
    sync = AsyncMock()
    monkeypatch.setattr(auth.llm, "ensure_user_exists", ensure)
    monkeypatch.setattr(auth.llm, "sync_user_team_memberships", sync)
    requests = mock_provider(monkeypatch)

    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://portal.example") as client:
        config = await client.get("/api/auth/config")
        assert config.json()["sso_enabled"] is True
        response = await client.get("/api/auth/login")
        query = parse_qs(urlsplit(response.headers["location"]).query)
        state = query["state"][0]
        assert query["audience"] == ["portal"]
        assert query["redirect_uri"] == ["https://portal.example/api/auth/callback"]
        assert query["client_id"] == ["generic-client"]
        assert query["scope"] == ["openid profile email"]
        assert query["code_challenge_method"] == ["S256"]
        assert "nonce" not in query
        response = await client.get("/api/auth/callback", params={"code": "authorization-code", "state": state})
        assert response.status_code == 307
        session = client.cookies.get("litegate_session")
        assert session
        user = auth.get_current_user(credentials=None, session_cookie=session)
        assert user.user_id == "employee-123"
        assert user.is_admin
        assert user.team_ids == ["team-engineering"]
        assert "litegate_oidc_state" not in client.cookies
        cookie = response.headers.get_list("set-cookie")[0]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie

    ensure.assert_awaited_once_with("employee-123", "alex@example.com")
    sync.assert_awaited_once_with("employee-123", "alex@example.com", ["team-engineering"])
    assert len(requests) == 2
    form = parse_qs(requests[0].content.decode())
    assert form["client_id"] == ["generic-client"]
    assert form["client_secret"] == ["test-provider-secret"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [challenge]
    assert requests[1].headers["authorization"] == "Bearer opaque-provider-token"


@pytest.mark.asyncio
async def test_basic_client_authentication_without_pkce(provider, monkeypatch):
    provider.generic_include_client_id = False
    provider.generic_client_use_pkce = False
    requests = mock_provider(monkeypatch)
    state = oidc.generate_state("generic")
    query = parse_qs(urlsplit(generic_sso.get_authorization_url(state)).query)
    claims = await generic_sso.get_user_claims("code", state)
    assert claims["sub"] == "employee-123"
    assert "code_challenge" not in query
    form = parse_qs(requests[0].content.decode())
    assert not {"client_id", "client_secret", "code_verifier"} & form.keys()
    credentials = base64.b64decode(requests[0].headers["authorization"].removeprefix("Basic ")).decode()
    assert credentials == "generic-client:test-provider-secret"


@pytest.mark.asyncio
async def test_basic_auth_form_encodes_oauth_credentials(provider, monkeypatch):
    provider.generic_include_client_id = False
    provider.generic_client_id = "client:with+reserved/id"
    provider.generic_client_secret = "a+b%secret / é"
    requests = mock_provider(monkeypatch)
    await generic_sso.get_user_claims("code", oidc.generate_state("generic"))
    credentials = base64.b64decode(requests[0].headers["authorization"].removeprefix("Basic ")).decode("ascii")
    encoded_id, encoded_secret = credentials.split(":")
    assert unquote_plus(encoded_id) == provider.generic_client_id
    assert unquote_plus(encoded_secret) == provider.generic_client_secret


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token", "userinfo", "message"),
    [
        ({}, None, "access token"),
        ({"access_token": []}, None, "access token"),
        ({"access_token": "opaque", "token_type": "MAC"}, None, "token type"),
        ([], None, "access token"),
        (None, [], "invalid UserInfo"),
        (None, {"mail": "alex@example.com"}, "user ID"),
        (None, {"identity": {"employee_id": {"bad": "id"}}}, "user ID"),
        (None, {"identity": {"employee_id": " "}}, "user ID"),
        (None, {"identity": {"employee_id": "u"}, "mail": []}, "invalid email"),
    ],
)
async def test_malformed_provider_responses_fail_closed(provider, monkeypatch, token, userinfo, message):
    mock_provider(monkeypatch, token=token, userinfo=userinfo)
    with pytest.raises(HTTPException, match=message) as exc:
        await generic_sso.get_user_claims("code", oidc.generate_state("generic"))
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_explicitly_unverified_email_is_rejected(provider, monkeypatch):
    mock_provider(monkeypatch, userinfo={"identity": {"employee_id": "u"}, "mail": "alex@example.com", "email_verified": False})
    with pytest.raises(HTTPException) as exc:
        await generic_sso.get_user_claims("code", oidc.generate_state("generic"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("verification", [True, False, None])
@pytest.mark.parametrize("required", [True, False])
async def test_email_verification_policy(provider, monkeypatch, verification, required):
    provider.generic_require_verified_email = required
    userinfo = {"identity": {"employee_id": "u"}, "mail": "alex@example.com"}
    if verification is not None:
        userinfo["email_verified"] = verification
    mock_provider(monkeypatch, userinfo=userinfo)
    state = oidc.generate_state("generic")
    if required and verification is False:
        with pytest.raises(HTTPException) as exc:
            await generic_sso.get_user_claims("code", state)
        assert exc.value.status_code == 403
    else:
        claims = await generic_sso.get_user_claims("code", state)
        assert claims["sub"] == "u"
        assert claims["email"] == "alex@example.com"


@pytest.mark.asyncio
async def test_unverified_email_opt_out_allows_callback_and_session(provider, monkeypatch):
    provider.generic_require_verified_email = False
    ensure = AsyncMock(return_value={"user_id": "u"})
    monkeypatch.setattr(auth.llm, "ensure_user_exists", ensure)
    mock_provider(monkeypatch, userinfo={"identity": {"employee_id": "u"}, "mail": "alex@example.com", "email_verified": False})
    state = oidc.generate_state("generic")
    response = await auth.callback("code", state, state_cookie=state)
    from http.cookies import SimpleCookie

    cookie = SimpleCookie(response.headers.getlist("set-cookie")[0])
    user = auth.get_current_user(credentials=None, session_cookie=cookie["litegate_session"].value)
    assert user.user_id == "u"
    assert user.email == "alex@example.com"
    assert user.is_admin is False
    ensure.assert_awaited_once_with("u", "alex@example.com")


@pytest.mark.asyncio
async def test_missing_email_does_not_prevent_login_or_promote_userinfo_role(provider, monkeypatch):
    ensure = AsyncMock(return_value={"user_id": "u"})
    monkeypatch.setattr(auth.llm, "ensure_user_exists", ensure)
    mock_provider(monkeypatch, userinfo={"identity": {"employee_id": "u"}, "role": "proxy_admin"})
    state = oidc.generate_state("generic")
    response = await auth.callback("code", state, state_cookie=state)
    from http.cookies import SimpleCookie

    cookie = SimpleCookie(response.headers.getlist("set-cookie")[0])
    user = auth.get_current_user(credentials=None, session_cookie=cookie["litegate_session"].value)
    assert user.email == ""
    assert user.is_admin is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 400, 401, 500])
async def test_provider_errors_do_not_expose_credentials(provider, monkeypatch, status):
    requests = mock_provider(monkeypatch, status=status)
    with pytest.raises(HTTPException) as exc:
        await generic_sso.get_user_claims("code", oidc.generate_state("generic"))
    assert exc.value.status_code == 502
    assert exc.value.detail == "Could not authenticate with the SSO provider"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_network_failure_is_sanitized(provider, monkeypatch):
    async def fail(*args, **kwargs):
        raise httpx.ConnectError("upstream secret")

    monkeypatch.setattr(httpx.AsyncClient, "post", fail)
    with pytest.raises(HTTPException, match="Could not authenticate"):
        await generic_sso.get_user_claims("code", oidc.generate_state("generic"))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["other-browser", "oidc-state", "tampered", "expired", "missing-cookie"])
async def test_invalid_state_never_contacts_provider(provider, monkeypatch, kind):
    state = oidc.generate_state("generic")
    cookie = state
    if kind == "other-browser":
        cookie = oidc.generate_state("generic")
    elif kind == "oidc-state":
        state = cookie = oidc.generate_state()
    elif kind == "tampered":
        state = cookie = state + "tampered"
    elif kind == "expired":
        monkeypatch.setattr("itsdangerous.timed.time.time", lambda: 9999999999)
    else:
        cookie = None
    exchange = AsyncMock()
    monkeypatch.setattr(generic_sso, "get_user_claims", exchange)
    with pytest.raises(HTTPException) as exc:
        await auth.callback("code", state, state_cookie=cookie)
    assert exc.value.status_code == 400
    exchange.assert_not_awaited()


def test_pkce_verifier_survives_secret_rotation(provider, monkeypatch):
    old_secret = "old-test-signing-secret-32-characters"
    state = URLSafeTimedSerializer(old_secret).dumps({"nonce": "random-nonce", "flow": "generic"})
    monkeypatch.setattr(provider, "jwt_secret", old_secret)
    verifier = oidc.state_pkce_verifier(state)
    monkeypatch.setattr(provider, "jwt_secret", "new-test-signing-secret-32-characters")
    monkeypatch.setattr(provider, "jwt_previous_secrets", old_secret)
    assert oidc.state_pkce_verifier(state) == verifier
    assert len(verifier) == 43
    assert verifier not in state


@pytest.mark.asyncio
async def test_required_group_mapping_rejects_generic_login_without_membership(provider, monkeypatch):
    provider.oidc_require_team_mapping = True
    provider.oidc_group_team_mapping = {"Finance": "team-finance"}
    ensure = AsyncMock()
    monkeypatch.setattr(auth.llm, "ensure_user_exists", ensure)
    mock_provider(monkeypatch)
    state = oidc.generate_state("generic")
    with pytest.raises(HTTPException) as exc:
        await auth.callback("code", state, state_cookie=state)
    assert exc.value.status_code == 403
    ensure.assert_not_awaited()
