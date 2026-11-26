# LiteGate nightly

> **Nightly build, not a stable release.** Built automatically from the
> `nightly` branch: the latest stable LiteGate plus features that wait on a
> change outside LiteGate. Use it to try those features; run a stable release
> in production.

## Highlights

- **Scheduled team budget windows.** One schedule of windows (for example
  weekday mornings or weekends), each with its own budget, that every team
  shares. Spend starts at $0 when a window opens. A short `teams` block
  overrides caps for the teams that differ, and admins can set a custom cap or
  unlimited per team.
- The Teams page shows the open window on every team: spend of its cap, what
  is left and when it resets. See
  [Scheduled team budget windows](../configuration.md#scheduled-team-budget-windows-nightly).

## Upgrade Notes

- Budget windows need a LiteLLM build with
  [BerriAI/litellm#54147](https://github.com/BerriAI/litellm/pull/54147).
  They are off unless `team_budget_windows` (`TEAM_BUDGET_WINDOWS`, Helm
  `config.teamBudgetWindows`) is set.
- Nightly images otherwise use the same configuration as the stable release
  they are based on.
- Each nightly is an immutable `nightly-YYYYMMDD-<sha>` image and git tag; the
  `nightly` image tag moves to the newest one. Pin the dated tag to stay on a
  build.
