"""Validate which GitHub Actions runs may publish release image tags."""

import argparse
import os
import re
from pathlib import Path

MANUAL_TAG = re.compile(r"^(?:test|dev)-[A-Za-z0-9][A-Za-z0-9._-]{0,122}$")


def validate(
    *,
    event: str,
    sha: str,
    main_sha: str,
    manual_tag: str,
    publish_latest: bool,
) -> bool:
    """Reject publication paths that could overwrite official tags unsafely."""
    if event == "push":
        return sha == main_sha

    if event != "workflow_dispatch":
        raise ValueError(f"unsupported publication event: {event}")
    if manual_tag and not MANUAL_TAG.fullmatch(manual_tag):
        raise ValueError("manual image tags must start with test- or dev-")
    if publish_latest and sha != main_sha:
        raise ValueError("manual latest publication must run from current main")
    return publish_latest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--manual-tag", default="")
    parser.add_argument("--publish-latest", default="false")
    args = parser.parse_args()
    publish_latest = validate(
        event=args.event,
        sha=args.sha,
        main_sha=args.main_sha,
        manual_tag=args.manual_tag,
        publish_latest=args.publish_latest.lower() == "true",
    )
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as result:
            result.write(f"publish_latest={str(publish_latest).lower()}\n")


if __name__ == "__main__":
    main()
