"""Extract a GitHub release body while avoiding duplicate Markdown titles."""

import sys
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]

source, destination = map(Path, sys.argv[1:3])
lines = source.read_text(encoding="utf-8").splitlines()
if lines and lines[0].startswith("# "):
    lines = lines[1:]
while lines and not lines[0].strip():
    lines.pop(0)
body = "\n".join(lines).rstrip() + "\n"


def versioned_link(match: re.Match) -> str:
    label, target = match.groups()
    if "://" in target or target.startswith(("#", "mailto:")):
        return match.group(0)
    path, separator, fragment = target.partition("#")
    relative = (source.parent / path).resolve().relative_to(ROOT).as_posix()
    url = f"https://github.com/brtydse100/litegate/blob/{source.stem}/{quote(relative)}"
    if separator:
        url += f"#{fragment}"
    return f"[{label}]({url})"


body = re.sub(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)", versioned_link, body)
destination.write_text(body, encoding="utf-8")
