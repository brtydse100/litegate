"""Indexed personal analytics snapshots in LiteGate's persistent SQLite store."""

import json
import math
from datetime import datetime, timezone

from app.services.local_users import connect


def create_tables(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS analytics_users (
        user_id TEXT PRIMARY KEY, email TEXT NOT NULL, auth_source TEXT NOT NULL, last_seen TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS analytics_snapshots (
        user_id TEXT PRIMARY KEY, refreshed_at TEXT NOT NULL, coverage_start TEXT NOT NULL,
        coverage_end TEXT NOT NULL, budgets_json TEXT NOT NULL, failed INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS analytics_daily (
        user_id TEXT NOT NULL, day TEXT NOT NULL, model TEXT NOT NULL,
        requests INTEGER NOT NULL, tokens INTEGER NOT NULL, input_tokens INTEGER,
        output_tokens INTEGER, cost REAL NOT NULL, PRIMARY KEY(user_id, day, model))""")


def create_failure_table(db) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS analytics_failures (user_id TEXT PRIMARY KEY, failed_at TEXT NOT NULL)")


def remember_user(user_id: str, email: str, auth_source: str) -> None:
    with connect() as db:
        db.execute(
            """INSERT INTO analytics_users VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET email=excluded.email,
            auth_source=excluded.auth_source, last_seen=excluded.last_seen""",
            (user_id, email, auth_source, datetime.now(timezone.utc).isoformat()),
        )


def users() -> list[str]:
    with connect() as db:
        return [row[0] for row in db.execute("SELECT user_id FROM analytics_users ORDER BY user_id")]


def publish(user_id: str, rows: list[dict], start: str, end: str, budgets: list[dict], refreshed_at: str) -> None:
    values = []
    for row in rows:
        numbers = [row[name] for name in ("requests", "tokens", "input_tokens", "output_tokens", "cost")]
        if not start <= row["day"] <= end or any(value is not None and (not math.isfinite(value) or value < 0) for value in numbers):
            raise ValueError("Invalid analytics snapshot")
        values.append((user_id, row["day"], row["model"], *numbers))
    encoded = json.dumps(budgets, allow_nan=False)
    with connect() as db:
        db.execute("DELETE FROM analytics_daily WHERE user_id=?", (user_id,))
        db.executemany("INSERT INTO analytics_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values)
        db.execute("DELETE FROM analytics_failures WHERE user_id=?", (user_id,))
        db.execute(
            """INSERT INTO analytics_snapshots VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET refreshed_at=excluded.refreshed_at,
            coverage_start=excluded.coverage_start, coverage_end=excluded.coverage_end,
            budgets_json=excluded.budgets_json, failed=0""",
            (user_id, refreshed_at, start, end, encoded),
        )


def failed(user_id: str) -> None:
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO analytics_failures VALUES (?, ?)", (user_id, datetime.now(timezone.utc).isoformat()))
        db.execute("UPDATE analytics_snapshots SET failed=1 WHERE user_id=?", (user_id,))


def metrics(rows: list[dict]) -> dict:
    result = {name: sum(row[name] for row in rows) for name in ("requests", "tokens", "cost")}
    for name in ("input_tokens", "output_tokens"):
        result[name] = sum(row[name] for row in rows) if all(row[name] is not None for row in rows) else None
    return result


def read(user_id: str, start: str, end: str) -> dict:
    with connect() as db:
        # Metadata, failures, and rows must come from the same WAL snapshot even
        # when the hourly collector commits a replacement between SELECTs.
        db.execute("BEGIN")
        snapshot = db.execute("SELECT * FROM analytics_snapshots WHERE user_id=?", (user_id,)).fetchone()
        failure = db.execute("SELECT failed_at FROM analytics_failures WHERE user_id=?", (user_id,)).fetchone()
        rows = [
            dict(row)
            for row in db.execute("SELECT * FROM analytics_daily WHERE user_id=? AND day BETWEEN ? AND ? ORDER BY day, model", (user_id, start, end))
        ]
    totals = [row for row in rows if row["model"] == ""]
    model_rows: dict[str, list[dict]] = {}
    for row in rows:
        if row["model"]:
            model_rows.setdefault(row["model"], []).append(row)
    refreshed = snapshot["refreshed_at"] if snapshot else None
    stale = not snapshot or bool(snapshot["failed"])
    if refreshed:
        stale = stale or (datetime.now(timezone.utc) - datetime.fromisoformat(refreshed)).total_seconds() > 7200
    return {
        "totals": metrics(totals),
        "daily": [{"date": row["day"], **metrics([row])} for row in totals],
        "models": [{"model": name, **metrics(batch)} for name, batch in sorted(model_rows.items())],
        "budgets": json.loads(snapshot["budgets_json"]) if snapshot else [],
        "last_refreshed_at": refreshed,
        "stale": stale,
        "coverage_start": snapshot["coverage_start"] if snapshot else None,
        "coverage_end": snapshot["coverage_end"] if snapshot else None,
        "available": snapshot is not None,
        "refresh_failed": failure is not None,
    }
