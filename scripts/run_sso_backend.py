"""Seed only synthetic local LiteLLM fixtures, then run the SSO test backend."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent.parent
URL = os.environ.get("LITELLM_URL", "http://127.0.0.1:4001")
MASTER = "sk-litegate-integration-master"
RESTART = ROOT / "backend/data/litegate-sso-test.restart"


def call(path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {MASTER}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def seed() -> None:
    if (
        os.environ.get("LITELLM_URL") != URL
        or os.environ.get("LITELLM_MASTER_KEY") != MASTER
        or URL not in {"http://127.0.0.1:4000", "http://127.0.0.1:4001"}
    ):
        raise RuntimeError(
            "SSO fixtures require the dedicated loopback integration LiteLLM"
        )
    realm = json.loads(
        (ROOT / "deploy/docker-compose/sso/litegate-sso-realm.json").read_text()
    )
    for user in realm["users"]:
        try:
            existing = call("/user/info?user_id=" + user["id"])
            if existing.get("user_info") is None:
                call(
                    "/user/new",
                    {
                        "user_id": user["id"],
                        "user_email": user["email"],
                        "user_role": "internal_user",
                        "auto_create_key": False,
                    },
                )
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            call(
                "/user/new",
                {
                    "user_id": user["id"],
                    "user_email": user["email"],
                    "user_role": "internal_user",
                    "auto_create_key": False,
                },
            )
    for team, admins in {
        "sso-test-engineering": [realm["users"][1], realm["users"][7]],
        "sso-test-platform": [realm["users"][2]],
        "sso-test-marketing": [],
    }.items():
        try:
            call("/team/info?team_id=" + team)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            call(
                "/team/new",
                {"team_id": team, "team_alias": team, "members_with_roles": []},
            )
        for user in admins:
            role = (
                "admin"
                if os.environ.get("SSO_TEST_TEAM_ADMINISTRATION") == "true"
                else "user"
            )
            info = call("/team/info?team_id=" + team)
            member = next(
                (
                    item
                    for item in info.get("team_info", {}).get("members_with_roles", [])
                    if item.get("user_id") == user["id"]
                ),
                None,
            )
            if member is None:
                call(
                    "/team/member_add",
                    {"team_id": team, "member": {"user_id": user["id"], "role": role}},
                )
            elif member.get("role") != role:
                call(
                    "/team/member_update",
                    {"team_id": team, "user_id": user["id"], "role": role},
                )


def seed_analytics() -> None:
    """Publish distinguishable synthetic snapshots; this does not test aggregation."""
    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(ROOT / "backend/data/litegate-sso-test.db") as db:
        for suffix, requests in [(4, 11), (6, 97)]:
            user_id = f"10000000-0000-4000-8000-{suffix:012d}"
            db.execute("DELETE FROM analytics_daily WHERE user_id=?", (user_id,))
            db.execute(
                "INSERT INTO analytics_daily VALUES (?, ?, '', ?, ?, ?, ?, ?)",
                (
                    user_id,
                    today,
                    requests,
                    requests * 10,
                    requests * 7,
                    requests * 3,
                    requests / 100,
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO analytics_snapshots VALUES (?, ?, ?, ?, '[]', 0)",
                (user_id, now, today, today),
            )


def serve() -> None:
    """Own the child process so a browser test can request an actual restart."""
    RESTART.unlink(missing_ok=True)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        str(ROOT / "backend"),
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--no-access-log",
    ]
    child = subprocess.Popen(command)
    try:
        while child.poll() is None:
            if RESTART.exists():
                wipe = RESTART.read_text().strip() == "wipe"
                child.terminate()
                child.wait(timeout=15)
                if wipe:
                    # Reproduce a deployment without persistent storage: the
                    # restarted backend starts from an empty database.
                    database = ROOT / "backend/data/litegate-sso-test.db"
                    for suffix in ("", "-wal", "-shm"):
                        Path(f"{database}{suffix}").unlink(missing_ok=True)
                child = subprocess.Popen(command)
                for _ in range(300):
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:8000/api/health/ready", timeout=1
                        ) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.1)
                else:
                    raise RuntimeError("SSO test backend did not restart")
                RESTART.unlink()
            time.sleep(0.1)
        raise RuntimeError(f"SSO test backend exited with {child.returncode}")
    finally:
        child.terminate()
        child.wait(timeout=15)


if __name__ == "__main__":
    if sys.argv[1:] == ["--seed-analytics"]:
        seed_analytics()
    else:
        seed()
        serve()
