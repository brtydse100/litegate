"""Durable revisioned budget proposals, period spend, and native apply journal."""

import json

from fastapi import HTTPException

from app.services import database


def create_tables(db) -> None:
    db.execute("""CREATE TABLE budget_policy (
        id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
        state_json TEXT NOT NULL)""")
    db.execute("INSERT INTO budget_policy VALUES (1, 0, ?)", (json.dumps({"envelopes": {}, "overrides": {}, "mode": "preview"}),))
    db.execute("""CREATE TABLE budget_spend (
        period TEXT NOT NULL, user_id TEXT NOT NULL, node_id TEXT NOT NULL,
        spent INTEGER NOT NULL CHECK(spent >= 0), PRIMARY KEY(period,user_id,node_id))""")
    db.execute("""CREATE TABLE budget_native_updates (
        revision INTEGER NOT NULL, target TEXT NOT NULL, desired_json TEXT NOT NULL,
        applied INTEGER NOT NULL DEFAULT 0, error TEXT,
        PRIMARY KEY(revision,target))""")


def _read(db) -> dict:
    row = db.execute("SELECT revision,state_json FROM budget_policy WHERE id=1").fetchone()
    return {**json.loads(row["state_json"]), "revision": row["revision"]}


def read() -> dict:
    with database.connect(read_only=True) as db:
        return _read(db)


def edit(revision: int, change) -> dict:
    """Validate and modify against the same reserved snapshot; exceptions roll back."""
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        state = _read(db)
        if state["revision"] != revision:
            raise HTTPException(409, "Budget revision changed; reload before saving")
        change(state)
        state["revision"] += 1
        db.execute(
            "UPDATE budget_policy SET revision=?,state_json=? WHERE id=1",
            (state["revision"], json.dumps({key: value for key, value in state.items() if key != "revision"}, sort_keys=True)),
        )
        return state


def observe(period: str, observations: list[dict]) -> None:
    """Only verified cumulative native spend from one aligned period belongs here."""
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for row in observations:
            if type(row["spent"]) is not int or row["spent"] < 0:
                raise ValueError("Spend observations require nonnegative integer units")
            db.execute(
                """INSERT INTO budget_spend VALUES (?,?,?,?)
                ON CONFLICT(period,user_id,node_id) DO UPDATE SET spent=MAX(spent,excluded.spent)""",
                (period, row["user_id"], row["node_id"], row["spent"]),
            )


def reservations(period: str, memberships: dict) -> dict:
    result = {}
    with database.connect(read_only=True) as db:
        for row in db.execute("SELECT user_id,node_id,spent FROM budget_spend WHERE period=?", (period,)):
            if memberships.get(row["user_id"]) != row["node_id"]:
                result[row["node_id"]] = result.get(row["node_id"], 0) + row["spent"]
    return result


def queue(revision: int, targets: list[dict]) -> None:
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if _read(db)["revision"] != revision:
            raise HTTPException(409, "Budget revision changed; reload before applying")
        for target in targets:
            key = json.dumps([target["team_id"], target.get("user_id")])
            encoded = json.dumps(target, sort_keys=True)
            previous = db.execute("SELECT desired_json FROM budget_native_updates WHERE revision=? AND target=?", (revision, key)).fetchone()
            if previous and previous[0] != encoded:
                raise HTTPException(409, "Native update differs from its persisted revision")
            db.execute("INSERT OR IGNORE INTO budget_native_updates(revision,target,desired_json) VALUES (?,?,?)", (revision, key, encoded))


def pending(revision: int) -> list[dict]:
    with database.connect(read_only=True) as db:
        return [
            json.loads(row[0])
            for row in db.execute("SELECT desired_json FROM budget_native_updates WHERE revision=? AND applied=0 ORDER BY target", (revision,))
        ]


def mark(revision: int, target: dict, *, error: str | None = None) -> None:
    with database.connect() as db:
        key = json.dumps([target["team_id"], target.get("user_id")])
        db.execute("UPDATE budget_native_updates SET applied=?,error=? WHERE revision=? AND target=?", (int(error is None), error, revision, key))
