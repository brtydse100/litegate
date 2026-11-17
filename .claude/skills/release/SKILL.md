---
name: release
description: Publish a new LiteGate release from main - version bump, release notes, changelog, tag, Docker image and GitHub Release. Use when the user asks to release, cut, tag or publish a new version or image (for example "release 2.21.0", "publish a new image", "make a release for the merged PR").
---

# Release LiteGate

Publishes a stable release the way AGENTS.md requires. Being asked to release is
the go-ahead to commit the release-prep commit to `main` and push the tag; still
stop and ask if any check fails or the version is ambiguous.

The tag push starts `.github/workflows/publish-container.yml`, which validates the
tag, builds and pushes `ghcr.io/brtydse100/litegate:X.Y.Z` for amd64 and arm64,
verifies the image, moves `latest` and `X.Y` and creates the GitHub Release from
`docs/releases/vX.Y.Z.md`. This skill prepares everything that workflow needs.

## 1. Check the starting point

```bash
git fetch origin --tags --prune
git switch main && git pull --ff-only
git status --short            # must have no tracked changes
cat VERSION                   # current version
git describe --tags --abbrev=0 # last release tag
gh run list --branch main --limit 3   # CI on the main head must be green
```

Wait for CI on the current `main` head to pass before tagging; never tag a red
or unfinished commit.

## 2. Choose the version

List what ships: `git log --oneline vPREV..origin/main`. Then use Semantic
Versioning. Use a patch for fixes and small visible changes, a minor for new
features or settings, and a major for breaking changes. If the user named a
version, use it. Ask only if the impact is genuinely unclear.

## 3. Prepare the files

1. `python scripts/version.py --set X.Y.Z` (updates VERSION, Helm chart, values
   and frontend package files; never edit them by hand).
2. `CHANGELOG.md`: rename the entries under `## [Unreleased]` into a new
   `## [X.Y.Z] - YYYY-MM-DD` section (keep `## [Unreleased]` empty above it). At
   the bottom, point `[Unreleased]` at `vX.Y.Z...HEAD` and add
   `[X.Y.Z]: .../compare/vPREV...vX.Y.Z`.
3. `docs/releases/vX.Y.Z.md`, copying the structure of the previous release:
   `# LiteGate vX.Y.Z`, `## Highlights` (short bold-led bullets),
   `## Release Artifacts` (the artifact table with the versioned image, current
   demo, `/blob/vX.Y.Z/docs/README.md`, `/tree/vX.Y.Z` and versioned license),
   optional `## Upgrade Notes`, then `**Details:**`, `**Changes:**`,
   `**Full Changelog**: [vPREV...vX.Y.Z](...)` and `## Contributors`. Keep prose
   under 300 words; detail belongs in the guides.
4. **Changes** must use verified facts only. For each merged PR in the range, take
   the exact title and author from `gh pr view N --json title,author`. For direct
   commits use the exact subject and author with a linked short SHA. Never invent
   titles, authors or numbers, and do not repeat a PR's own commits.
5. `docs/releases/README.md`: add a row for the version at the top of the table.

## 4. Validate

```bash
python scripts/version.py --check
python scripts/check_docs.py
python -m pytest -q scripts
helm lint deploy/helm/litegate
python scripts/release_body.py docs/releases/vX.Y.Z.md /tmp/release.md   # renders cleanly
```

If code changed since the last full run, also run the backend and frontend
suites (see AGENTS.md **Commands**). Fix every failure before continuing.

## 5. Publish

```bash
git add -A CHANGELOG.md VERSION deploy/helm/litegate docs/releases frontend/package.json frontend/package-lock.json
git commit -m "release: prepare vX.Y.Z <short summary>"
git push origin main
# wait for CI on this commit to pass (gh run list --commit <sha>)
git tag -a vX.Y.Z -m "LiteGate vX.Y.Z"
git push origin vX.Y.Z
```

The tag must point at the current `main` head and match `VERSION`, or the publish
workflow refuses it.

## 6. Verify and report

```bash
gh run watch <publish run id> --exit-status
gh release view vX.Y.Z
docker buildx imagetools inspect ghcr.io/brtydse100/litegate:X.Y.Z   # amd64 + arm64
```

Confirm `latest` and `X.Y` resolve to the same digest. Report the release link,
the `docker pull` command and anything that did not pass. Never claim a release
is published until the workflow and these checks succeed.
