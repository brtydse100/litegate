"""Application version loaded from the repository's single source of truth."""

from pathlib import Path


def _read_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0+unknown"


VERSION = _read_version()
