# Cost display and team budget authority

Approved scope: render currency with exactly two fractional digits without
changing stored precision. Delegated team administrators redistribute an existing
team allowance among members and child teams; its assigned total stays read-only.
Parent and system administrators retain assignment authority.

1. Add failing display regressions for ordinary, zero and sub-cent amounts.
   Update shared currency formatting and budget summaries, preserving precise
   numeric editing and payloads. Update existing UI/browser assertions.
2. Verify own-team denial and permitted child/member allocation through backend
   API tests, including unchanged state after rejection and conservation of the
   parent budget. Keep authorization enforced in backend handlers; clarify UI
   labels for assigned totals versus child allocations. Preserve existing working
   rules rather than redesigning them.
3. Update focused documentation and Unreleased notes. Run backend formatting,
   relevant/full tests, frontend format/lint/typecheck/tests/build, browser checks
   and repository/deployment checks. Open a new PR from validated main, publish
   its immutable preview and verify the image revision before handoff.

No new dependency, schema or deployment setting is expected.
