import pytest
from fastapi import HTTPException
from app.rate_limit import (
    _login_failures,
    _MAX_KEY_OPS,
    _MAX_LOGIN_FAILURES,
    _key_ops,
    check_key_rate_limit,
    check_login_rate_limit,
    clear_login_failures,
    key_rate_limit_status,
    record_login_failure,
)


def setup_function():
    _key_ops.clear()
    _login_failures.clear()


def test_allows_ops_under_limit():
    for _ in range(_MAX_KEY_OPS - 1):
        check_key_rate_limit("user-a")  # must not raise


def test_blocks_at_limit():
    for _ in range(_MAX_KEY_OPS):
        check_key_rate_limit("user-b")
    with pytest.raises(HTTPException) as exc:
        check_key_rate_limit("user-b")
    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "60"}
    assert key_rate_limit_status("user-b") == {"limit": 5, "remaining": 0, "retry_after": 60}


def test_users_are_isolated():
    for _ in range(_MAX_KEY_OPS):
        check_key_rate_limit("user-c")
    check_key_rate_limit("user-d")  # unaffected by user-c — must not raise


def test_window_expiry(monkeypatch):
    import app.rate_limit as rl

    fake_now = [0.0]
    monkeypatch.setattr(rl, "monotonic", lambda: fake_now[0])

    for _ in range(_MAX_KEY_OPS):
        rl.check_key_rate_limit("user-e")

    fake_now[0] = rl._KEY_WINDOW + 1.0
    rl.check_key_rate_limit("user-e")  # old entries expired — must not raise


def test_failed_logins_are_throttled_and_success_clears_them():
    client_id = "192.0.2.10"
    for _ in range(_MAX_LOGIN_FAILURES):
        check_login_rate_limit(client_id)
        record_login_failure(client_id)

    with pytest.raises(HTTPException) as exc:
        check_login_rate_limit(client_id)

    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0

    clear_login_failures(client_id)
    check_login_rate_limit(client_id)
