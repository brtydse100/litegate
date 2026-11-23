# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **People who use AI models at work.** They sign in with SSO or a local
  account, create or copy one personal LiteLLM key, and check how much of
  their budget is left. They visit briefly and want to leave quickly.
- **Team owners.** They see their own part of the organization, split their
  team's budget among sub-teams and members, and check usage.
- **Administrators.** They manage local users, LiteLLM teams, installation-wide
  keys (including bulk edits), the organization tree, audit history and
  operational status.

## Product Purpose

LiteGate is a small, security-focused access layer for LiteLLM. It gives each
person one simple page for a governed virtual key, and gives administrators
narrowly scoped controls, so nobody needs the LiteLLM admin dashboard or the
master key. LiteLLM remains the source of truth for models, budgets, spend and
routing. Success: a user gets a working key in one click, and an administrator
changes policy without touching LiteLLM directly.

## Positioning

A narrow, governed self-service door to LiteLLM rather than a second admin
console: personal keys inherit team budgets and model policy from SSO groups,
and spend carries over when a key is replaced.

## Operating Context

- Browser portal with an HttpOnly session cookie; OIDC or local sign-in.
- Desktop browsers at work are the main scene; phones must still work.
- A public interactive demo (`VITE_DEMO_MODE=true`) runs the real frontend on
  synthetic data, with a role switch for User, Owner and Admin.

## Capabilities and Constraints

- Screens: Sign in, My key, Analytics, Organization, Teams, Keys, People,
  Audit log, Status.
- A new key secret is shown only in its creation response.
- Ordinary users and LiteLLM-key identities never see administrative or bulk
  key operations.
- Light and dark themes are both supported.
- Stack: React, TypeScript, Tailwind CSS, lucide-react icons.

## Brand Commitments

- Name: LiteGate. A configured logo can replace the default mark.
- The interface follows Apple's Human Interface Guidelines for layout,
  typography, spacing, controls and feedback (user decision, November 2026).
- Plain, direct wording; existing labels and messages are kept.

## Evidence on Hand

- Demo data in `frontend/src/demo/` is synthetic and must stay that way.
- Screenshots for docs live in `docs/media/`.

## Product Principles

1. The ordinary user's path stays short: sign in, see the key, leave.
2. Never weaken the authorization boundary for convenience.
3. Show the facts LiteLLM enforces (budget, spend, models, limits) plainly.
4. Administrative power is explicit, scoped and audited.

## Accessibility & Inclusion

Keyboard operable, visible focus, WCAG AA contrast in both themes, and
forced-colours support for custom controls.
