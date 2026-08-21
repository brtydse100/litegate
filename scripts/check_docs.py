"""Fail when a local Markdown link points at a missing file."""

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
failures: list[str] = []

for path in [*ROOT.glob("*.md"), *ROOT.glob("docs/**/*.md")]:
    text = path.read_text(encoding="utf-8")
    for target in LINK.findall(text):
        target = target.strip().strip("<>").split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        resolved = (path.parent / unquote(target)).resolve()
        if not resolved.exists():
            failures.append(f"{path.relative_to(ROOT)} -> {target}")

if failures:
    raise SystemExit("Broken local Markdown links:\n" + "\n".join(failures))
print("Local Markdown links are valid")
