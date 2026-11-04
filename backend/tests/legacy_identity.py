"""Seed records written by LiteGate 2.15.0 for upgrade tests."""

import hashlib
from app.services import local_users, sso_identity as store


def reserve(provider, email):
    store.initialize_identity_store()
    email = email.strip().casefold()
    user_id = "litegate-org:" + hashlib.sha256(f"{provider}:{email}".encode()).hexdigest()
    with local_users.connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO sso_reservations(provider,email,user_id,ownership_token) VALUES (?,?,?,?)",
            (provider, email, user_id, "legacy-ownership-token"),
        )
    return store.reservation(provider, email)


def mark_reservation(provider, email, status, candidate_id=""):
    with local_users.connect() as db:
        db.execute("UPDATE sso_reservations SET status=?,candidate_id=? WHERE provider=? AND email=?", (status, candidate_id, provider, email))
