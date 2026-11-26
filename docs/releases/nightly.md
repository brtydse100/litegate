# LiteGate nightly

> **Nightly build, not a stable release.** Built automatically from the
> `nightly` branch: the latest stable LiteGate plus features that wait on a
> change outside LiteGate. Use it to try those features; run a stable release
> in production.

## Highlights

- Nothing beyond the latest stable release yet.

## Upgrade Notes

- Nightly images use the same configuration as the stable release they are
  based on. Features listed above are off unless configured.
- Each nightly is an immutable `nightly-YYYYMMDD-<sha>` image and git tag; the
  `nightly` image tag moves to the newest one. Pin the dated tag to stay on a
  build.
