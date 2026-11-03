from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import settings
from app.services import local_users
from app.services import sso_identity as store


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "identity.db"))


def test_unconfigured_lookup_does_not_create_database():
    assert store.lookup_binding("provider", "subject") is None
    assert not local_users._db_path().exists()


def test_initialization_preserves_local_rows_and_reservations():
    local_users.init_db()
    local = local_users.create_user("existing", "existing@example.com", "test-password")
    reservation = store.reserve("provider", " Alice@Example.com ")
    store.initialize_identity_store()
    assert store.reserve("provider", "alice@example.com") == reservation
    assert reservation["user_id"].startswith("litegate-org:")
    assert reservation["ownership_token"]
    assert store.reserve("other-provider", "alice@example.com")["user_id"] != reservation["user_id"]
    assert local_users.get_user("existing") == local


def test_binding_cannot_switch_subject_email_or_canonical_user():
    store.bind("provider", "subject", "alice@example.com", "canonical")
    assert store.lookup_binding("provider", "subject")["user_id"] == "canonical"
    store.bind("provider", "subject", "alice@example.com", "canonical")
    for args in [
        ("provider", "subject", "alice@example.com", "different"),
        ("provider", "other", "alice@example.com", "different"),
        ("other", "subject", "alice@example.com", "canonical"),
    ]:
        with pytest.raises(store.IdentityConflict):
            store.bind(*args)


def test_concurrent_claims_select_one_subject():
    store.initialize_identity_store()

    def claim(subject):
        try:
            store.bind("provider", subject, "alice@example.com", "canonical")
            return True
        except store.IdentityConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, ["one", "two"])) == [False, True]


def test_superseded_reservation_remains_durable():
    reservation = store.reserve("provider", "alice@example.com")
    store.bind("provider", "subject", "alice@example.com", "subject")
    assert store.reservation("provider", "alice@example.com")["status"] == "superseded"
    assert store.reserve("provider", "alice@example.com")["user_id"] == reservation["user_id"]
