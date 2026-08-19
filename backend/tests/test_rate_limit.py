import pytest
from fastapi import HTTPException
from app.rate_limit import check_key_rate_limit, _key_ops, _MAX_KEY_OPS


def setup_function():
    _key_ops.clear()


def test_allows_ops_under_limit():
    for _ in range(_MAX_KEY_OPS - 1):
        check_key_rate_limit("user-a")  # must not raise


def test_blocks_at_limit():
    for _ in range(_MAX_KEY_OPS):
        check_key_rate_limit("user-b")
    with pytest.raises(HTTPException) as exc:
        check_key_rate_limit("user-b")
    assert exc.value.status_code == 429


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
