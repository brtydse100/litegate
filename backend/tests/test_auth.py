import jwt
import pytest
from jwt import InvalidTokenError

from app.dependencies import decode_portal_token
from app.config import settings


def test_portal_token_round_trip():
    token = jwt.encode(
        {"sub": "user-1", "email": "user@example.com", "role": "admin", "auth_source": "sso"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    user = decode_portal_token(token)
    assert user.user_id == "user-1"
    assert user.is_admin is True


def test_portal_token_requires_subject():
    token = jwt.encode({"email": "nobody@example.com"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError):
        decode_portal_token(token)
