import sqlite3

import pytest

from app import maintenance


def _database(path, marker: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES (?)", (marker,))


def _marker(path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT value FROM marker").fetchone()[0]


def test_backup_is_consistent_and_verifiable(tmp_path):
    source = tmp_path / "live.db"
    destination = tmp_path / "backups" / "snapshot.db"
    _database(source, "live-data")

    maintenance.backup_database(source, destination)

    assert destination.exists()
    assert _marker(destination) == "live-data"
    assert maintenance.verify_database(destination) == "ok"


def test_restore_requires_confirmation_and_preserves_previous_database(tmp_path):
    backup = tmp_path / "snapshot.db"
    destination = tmp_path / "live.db"
    safety = tmp_path / "before-restore.db"
    _database(backup, "backup-data")
    _database(destination, "current-data")

    with pytest.raises(ValueError, match="confirmation"):
        maintenance.restore_database(backup, destination, safety, confirmed=False)
    assert _marker(destination) == "current-data"

    maintenance.restore_database(backup, destination, safety, confirmed=True)

    assert _marker(destination) == "backup-data"
    assert _marker(safety) == "current-data"
