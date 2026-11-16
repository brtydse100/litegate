# Compact Release Notes Implementation Plan

> Execute inline using the existing isolated PR #49 worktree.

**Goal:** Apply the approved vLLM-inspired, concise format to all historical
release notes and their GitHub descriptions; prepare unreleased PR #49 notes.

**Design:** Start with Highlights, followed by Release Artifacts and optional
Upgrade Notes. Use short grouped bullets and links to detailed guides. Preserve
release-specific warnings, attribution, commit/PR references and artifact URLs.
Keep Contributors and Full Changelog. Do not bump VERSION, merge, retag historical
releases, or publish an unreleased stable image. No dependencies are required.

1. Update `scripts/test_release_notes.py` to require Highlights first, compact
   content and the new artifact heading; observe failures on the old notes.
2. Rewrite `docs/releases/v*.md`; update `AGENTS.md` and the release index;
   add `docs/releases/unreleased-pr-49.md` with real preview/source links.
3. Run release/script tests, Markdown/version checks and required format/lint/
   typecheck checks. Review preserved warnings and references against Git HEAD.
4. Synchronize existing published release bodies using `scripts/release_body.py`
   and `gh release edit --notes-file`; verify the remote bodies match exactly.
5. Commit/push the PR update and publish/verify a new immutable preview image.

Review focus: historical upgrade commands and removed settings, versioned links,
accurate attribution, no unpublished artifacts advertised as released, and
GitHub descriptions matching checked-in notes. A release-note rewrite does not
change release tags or historical source archives.

Execution: format tests failed on all old headings before the rewrite, then all
30 script tests passed. Format, lint, typecheck, backend formatting, Markdown and
version checks passed. Audited all original links and artifact tables against
HEAD and verified the versioned artifact files in Git. Independent review found
no material issues; clarified failed-policy migration wording and counted only
artifact table rows outside the 300-word limit.

All 26 published GitHub descriptions were backed up, regenerated, updated and
verified against the local notes. Titles, tags, publication dates and release
flags were unchanged. No historical tags or images were replaced.

Review rulings: remote synchronization was pending during independent review and
was verified by the executor afterward. Underlying PR implementation remains
covered by its existing reviews and green CI; this task changes release material
only. Inherited prepared-release labels are historical metadata and are retained.
The temporary rewrite generator was removed. No deferred findings in this task.

Delivery adjustment: PR #49 was already merged at 8c18314 before this task's
release-note commit. Reapplied the docs-only commit on validated origin/main in
`docs/compact-release-notes` for a separate follow-up PR. The release draft now
describes PR #49 as merged but unreleased. VERSION remains unchanged, as approved.
