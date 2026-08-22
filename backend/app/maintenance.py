"""Safe SQLite backup, verification, and offline restore commands."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

from app.config import settings


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def verify_database(path: str | Path) -> str:
    database = _resolved(path)
    if not database.is_file():
        raise ValueError(f"Database does not exist: {database}")
    try:
        with closing(sqlite3.connect(database)) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Database verification failed: {exc}") from exc
    status = str(result[0]) if result else "missing result"
    if status != "ok":
        raise ValueError(f"Database verification failed: {status}")
    return status


def backup_database(source: str | Path, destination: str | Path) -> Path:
    source_path = _resolved(source)
    destination_path = _resolved(destination)
    if source_path == destination_path:
        raise ValueError("Backup destination must differ from the live database")
    if not source_path.is_file():
        raise ValueError(f"Database does not exist: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_name(f".{destination_path.name}.{os.getpid()}.tmp")
    try:
        if temporary.exists():
            temporary.unlink()
        with (
            closing(sqlite3.connect(source_path)) as source_db,
            closing(sqlite3.connect(temporary)) as backup_db,
        ):
            source_db.backup(backup_db)
        verify_database(temporary)
        os.replace(temporary, destination_path)
        os.chmod(destination_path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination_path


def restore_database(
    source: str | Path,
    destination: str | Path,
    safety_backup: str | Path,
    *,
    confirmed: bool,
) -> Path:
    if not confirmed:
        raise ValueError("Restore requires explicit confirmation")
    source_path = _resolved(source)
    destination_path = _resolved(destination)
    safety_path = _resolved(safety_backup)
    if len({source_path, destination_path, safety_path}) != 3:
        raise ValueError("Restore source, destination, and safety backup must be different files")
    verify_database(source_path)
    if destination_path.exists():
        backup_database(destination_path, safety_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    # Restore is explicitly offline. SQLite's backup API safely replaces the
    # database contents without relying on platform-specific file replacement.
    with (
        closing(sqlite3.connect(source_path)) as source_db,
        closing(sqlite3.connect(destination_path)) as destination_db,
    ):
        source_db.backup(destination_db)
    verify_database(destination_path)
    os.chmod(destination_path, 0o600)
    return destination_path


def _default_safety_backup(destination: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return destination.with_name(f"{destination.stem}.pre-restore-{timestamp}{destination.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    backup = commands.add_parser("backup", help="Create and verify a consistent SQLite backup")
    backup.add_argument("output", type=Path)
    backup.add_argument("--source", type=Path, default=Path(settings.local_users_db_path))

    verify = commands.add_parser("verify", help="Run SQLite integrity verification")
    verify.add_argument("database", type=Path)

    restore = commands.add_parser("restore", help="Restore while preserving the current database")
    restore.add_argument("input", type=Path)
    restore.add_argument("--destination", type=Path, default=Path(settings.local_users_db_path))
    restore.add_argument("--safety-backup", type=Path)
    restore.add_argument("--confirm", action="store_true")

    args = parser.parse_args()
    if args.command == "backup":
        result = backup_database(args.source, args.output)
        print(f"Verified backup written to {result}")
    elif args.command == "verify":
        verify_database(args.database)
        print(f"Database is valid: {_resolved(args.database)}")
    else:
        destination = _resolved(args.destination)
        safety = args.safety_backup or _default_safety_backup(destination)
        result = restore_database(
            args.input,
            destination,
            safety,
            confirmed=args.confirm,
        )
        print(f"Database restored to {result}; previous database saved to {_resolved(safety)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
