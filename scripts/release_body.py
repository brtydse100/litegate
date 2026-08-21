"""Extract a GitHub release body while avoiding duplicate Markdown titles."""

import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:3])
lines = source.read_text(encoding="utf-8").splitlines()
if lines and lines[0].startswith("# "):
    lines = lines[1:]
while lines and not lines[0].strip():
    lines.pop(0)
destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
