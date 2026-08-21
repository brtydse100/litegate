"""Check or update every checked-in LiteGate version reference."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"


def expected_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def check() -> list[str]:
    version = expected_version()
    failures: list[str] = []
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    chart = (ROOT / "deploy/helm/litegate/Chart.yaml").read_text(encoding="utf-8")
    values = (ROOT / "deploy/helm/litegate/values.yaml").read_text(encoding="utf-8")
    checks = {
        "frontend/package.json": package.get("version"),
        "frontend/package-lock.json": lock.get("version"),
        "frontend/package-lock.json packages['']": lock.get("packages", {}).get("", {}).get("version"),
    }
    for name, actual in checks.items():
        if actual != version:
            failures.append(f"{name}: expected {version}, found {actual}")
    if not re.search(rf'^appVersion:\s*["\']?{re.escape(version)}["\']?\s*$', chart, re.MULTILINE):
        failures.append(f"deploy/helm/litegate/Chart.yaml: appVersion is not {version}")
    if not re.search(rf'^\s*tag:\s*["\']?{re.escape(version)}["\']?', values, re.MULTILINE):
        failures.append(f"deploy/helm/litegate/values.yaml: image tag is not {version}")
    return failures


def set_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Version must be stable SemVer: X.Y.Z")
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    for name in ("package.json", "package-lock.json"):
        path = ROOT / "frontend" / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        if name == "package-lock.json":
            data["packages"][""]["version"] = version
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    chart = ROOT / "deploy/helm/litegate/Chart.yaml"
    chart.write_text(re.sub(r'^appVersion:.*$', f'appVersion: "{version}"', chart.read_text(encoding="utf-8"), flags=re.MULTILINE), encoding="utf-8")
    values = ROOT / "deploy/helm/litegate/values.yaml"
    values.write_text(re.sub(r'^(\s*tag:)\s*[^\n#]+', rf'\1 "{version}"  ', values.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--set", dest="new_version")
    args = parser.parse_args()
    if args.new_version:
        set_version(args.new_version)
    failures = check()
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Version references agree on {expected_version()}")


if __name__ == "__main__":
    main()
