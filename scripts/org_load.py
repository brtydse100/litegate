"""Measure LiteGate against a large synthetic organization on the test LiteLLM.

Runs LiteGate's own services in-process against the dedicated loopback
integration gateway (see docs/testing.md) with enforced organization budgets,
and reports wall time and LiteLLM requests for sign-in, regeneration, the
background synchronization and the organization pages.

    python scripts/org_load.py --users 400 --teams 20
    python scripts/org_load.py --cleanup

Only synthetic ``litegate-load-*`` users, keys and teams are created.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:4001"
MASTER = "sk-litegate-integration-master"
PREFIX = "litegate-load"
WORK = Path(tempfile.gettempdir()) / PREFIX


def call(path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {MASTER}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def hierarchy(teams: int) -> dict:
    departments = max(1, teams // 5)
    return {
        "levels": [
            {
                "name": "Department",
                "groups": [
                    {
                        "members": [
                            {
                                "name": f"Load department {d}",
                                "litellmTeamId": f"{PREFIX}-dept-{d}",
                                "budget": {"duration": "30d"},
                            }
                            for d in range(departments)
                        ]
                    }
                ],
            },
            {
                "name": "Team",
                "groups": [
                    {
                        "parent": f"Load department {d}",
                        "members": [
                            {
                                "name": f"Load team {t}",
                                "litellmTeamId": f"{PREFIX}-team-{t}",
                                "ssoGroups": [f"{PREFIX}-team-{t}"],
                                "budget": {"groupTotal": 1000, "perUser": 200},
                            }
                            for t in range(teams)
                            if t % departments == d
                        ],
                    }
                    for d in range(departments)
                ],
            },
        ]
    }


def configure(users: int, teams: int) -> None:
    WORK.mkdir(exist_ok=True)
    (WORK / "organization.json").write_text(json.dumps(hierarchy(teams)))
    database = WORK / "load.db"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{database}{suffix}").unlink(missing_ok=True)
    os.environ.update(
        LITELLM_URL=URL,
        LITELLM_MASTER_KEY=MASTER,
        JWT_SECRET="litegate-load-test-jwt-secret-at-least-32-characters",
        LOCAL_USERS_DB_PATH=str(database),
        ORGANIZATION_HIERARCHY_FILE=str(WORK / "organization.json"),
        HIERARCHICAL_BUDGETS_ENABLED="true",
        HIERARCHICAL_BUDGETS_ENFORCED="true",
        KEY_ROTATION_SETTLE_SECONDS=os.environ.get("KEY_ROTATION_SETTLE_SECONDS", "12"),
    )
    sys.path.insert(0, str(ROOT / "backend"))


class Meter:
    def __init__(self):
        self.calls: Counter = Counter()

    async def hook(self, request):
        self.calls[request.url.path] += 1

    def reset(self) -> None:
        self.calls.clear()

    def total(self) -> int:
        return sum(self.calls.values())


async def timed(meter: Meter, label: str, operation, results: dict):
    meter.reset()
    started = time.perf_counter()
    value = await operation()
    results[label] = {
        "seconds": round(time.perf_counter() - started, 2),
        "litellm_requests": meter.total(),
    }
    print(
        f"{label:<45} {results[label]['seconds']:>8.2f} s {results[label]['litellm_requests']:>7} LiteLLM requests",
        flush=True,
    )
    return value


async def run(users: int, teams: int, concurrent: int) -> dict:
    from app.services import (
        database,
        litellm,
        litellm_client,
        organization_reports as reports,
        organization_sync as sync,
    )

    database.initialize()
    await litellm_client.start_client()
    meter = Meter()
    litellm_client._shared_client.event_hooks["request"].append(meter.hook)
    results: dict = {"users": users, "teams": teams}
    ids = [f"{PREFIX}-user-{n:04d}" for n in range(users)]

    async def setup():
        for n, user_id in enumerate(ids):
            await sync.record_identity(
                user_id,
                f"{user_id}@example.invalid",
                "sso",
                [f"{PREFIX}-team-{n % teams}"],
            )
        await sync.reconcile()  # creates the teams and memberships
        semaphore = asyncio.Semaphore(10)

        async def key(n, user_id):
            async with semaphore:
                if not await litellm.list_user_keys(user_id):
                    await litellm.generate_key(
                        user_id,
                        f"{user_id}@example.invalid",
                        f"{PREFIX}-team-{n % teams}",
                        initial_spend=0.01,
                    )

        await asyncio.gather(*(key(n, user_id) for n, user_id in enumerate(ids)))
        await sync.reconcile()  # applies the enforced shares to every key

    await timed(meter, "setup (identities, teams, keys)", setup, results)
    await timed(meter, "background synchronization pass", sync.reconcile, results)

    returning = ids[1]
    group = [f"{PREFIX}-team-{1 % teams}"]

    async def sign_in():
        await sync.record_identity(
            returning, f"{returning}@example.invalid", "sso", group
        )
        return await sync.synchronize_user(returning)

    await timed(meter, "sign-in (returning member)", sign_in, results)

    async def sign_in_during_sync():
        background = asyncio.create_task(sync.reconcile())
        await asyncio.sleep(0.2)
        started = time.perf_counter()
        await sign_in()
        waited = time.perf_counter() - started
        await background
        return waited

    waited = await timed(
        meter,
        "sign-in while synchronization runs (total)",
        sign_in_during_sync,
        results,
    )
    results["sign_in_during_sync_seconds"] = round(waited, 2)
    print(f"{'  of which the sign-in itself':<45} {waited:>8.2f} s", flush=True)

    moved = ids[-1]

    async def sign_in_after_move():
        # A changed group takes the full path: lock, re-read the affected groups.
        await sync.record_identity(
            moved, f"{moved}@example.invalid", "sso", [f"{PREFIX}-team-{users % teams}"]
        )
        return await sync.synchronize_user(moved)

    await timed(
        meter, "sign-in after moving to another team", sign_in_after_move, results
    )

    async def regenerate_many():
        durations = []

        async def one(user_id):
            started = time.perf_counter()
            await sync.rotate_key(
                user_id,
                f"{user_id}@example.invalid",
                None,
                key_alias=f"{user_id}'s key",
            )
            durations.append(time.perf_counter() - started)

        outcomes = await asyncio.gather(
            *(one(user_id) for user_id in ids[2 : 2 + concurrent]),
            return_exceptions=True,
        )
        failures = [repr(item) for item in outcomes if isinstance(item, BaseException)]
        return durations, failures

    durations, failures = await timed(
        meter,
        f"{concurrent} simultaneous regenerations (total)",
        regenerate_many,
        results,
    )
    if durations:
        results["regeneration_seconds"] = {
            "median": round(statistics.median(durations), 2),
            "max": round(max(durations), 2),
        }
        print(
            f"{'  per person median / slowest':<45} {statistics.median(durations):>8.2f} / {max(durations):.2f} s",
            flush=True,
        )
    results["regeneration_failures"] = failures
    for failure in failures[:3]:
        print("  failure:", failure[:200])

    today = datetime.now(timezone.utc).date()
    await timed(meter, "organization page: overview", reports.overview, results)
    await timed(
        meter,
        "organization page: top-level groups",
        lambda: reports.children(None),
        results,
    )
    reports._usage_cache.clear()
    await timed(
        meter,
        "organization page: 30-day usage",
        lambda: reports.usage(None, today - timedelta(days=29), today),
        results,
    )
    await timed(
        meter,
        "organization page: users (first page)",
        lambda: reports.users(None, 1, 50),
        results,
    )
    await litellm_client.close_client()
    return results


def cleanup() -> None:
    for page in range(1, 100):
        data = call(f"/key/list?page={page}&size=100&return_full_object=true")
        keys = [
            k.get("token")
            for k in data.get("keys", [])
            if str(k.get("user_id") or "").startswith(PREFIX)
        ]
        if keys:
            call("/key/delete", {"keys": keys})
        if page >= (data.get("total_pages") or 1):
            break
    users = []
    for page in range(1, 1000):
        data = call(f"/user/list?page={page}&page_size=100")
        users += [
            u["user_id"]
            for u in data.get("users", [])
            if u["user_id"].startswith(PREFIX)
        ]
        if page >= (data.get("total_pages") or 1):
            break
    if users:
        call("/user/delete", {"user_ids": users})
    teams = [
        t["team_id"]
        for t in call("/team/list")
        if str(t.get("team_id")).startswith(PREFIX)
    ]
    if teams:
        call("/team/delete", {"team_ids": teams})
    print(f"Removed {len(users)} users and {len(teams)} teams")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--users", type=int, default=400)
    parser.add_argument("--teams", type=int, default=20)
    parser.add_argument(
        "--concurrent", type=int, default=20, help="simultaneous regenerations"
    )
    parser.add_argument("--output", help="write the measurements as JSON")
    parser.add_argument(
        "--cleanup", action="store_true", help="remove the synthetic load fixtures"
    )
    args = parser.parse_args()
    if args.cleanup:
        cleanup()
        return
    configure(args.users, args.teams)
    results = asyncio.run(run(args.users, args.teams, args.concurrent))
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
