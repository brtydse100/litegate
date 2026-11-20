import type { BudgetGroup, BudgetView, PerUserLimit } from "../types/budgets";
import { demoGroups, demoMembers } from "./organization";

/**
 * Browser-only budget planning, following the backend's rules: child
 * allocations and manual overrides are reserved first and the rest is shared
 * equally by other direct members, capped by the per-user limit. Delegated
 * owners redistribute inside their scope but cannot change their own team's
 * assigned total, raise their own allowance or set per-user limits.
 */

const ALLOCATION_ERROR =
  "Assigned envelope cannot cover child budgets, manual allocations, and consumed spend";

// Synthetic envelopes in cents: each team's share of its department.
const initialEnvelopes: Record<string, number> = {
  engineering: 100000,
  marketing: 50000,
  infrastructure: 40000,
  applications: 30000,
  digital: 20000,
  platform: 25000,
  cloud: 12000,
  backend: 20000,
  social: 15000,
};

let state = {
  revision: 1,
  envelopes: { ...initialEnvelopes },
  overrides: {} as Record<string, number>,
  perUser: {} as Record<string, number | null>,
};

/** Restores the seeded budgets, for tests. */
export function resetDemoBudgets() {
  state = {
    revision: 1,
    envelopes: { ...initialEnvelopes },
    overrides: {},
    perUser: {},
  };
}

export interface BudgetActor {
  admin: boolean;
  userId: string;
  /** Whether a group is inside the actor's organization scope. */
  allows: (groupId: string) => boolean;
}

type State = typeof state;
type Row = {
  assigned: number;
  allocated: number | null;
  remainder: number | null;
  shortfall: number;
  users: Record<string, number | null>;
};

const toCents = (value: unknown) => Math.round(Number(value) * 100);
const perUserOf = (current: State, id: string) =>
  id in current.perUser
    ? current.perUser[id]
    : (demoGroups.find((group) => group.id === id)?.per_user ?? null);

function allocate(current: State) {
  const rows: Record<string, Row> = {};
  for (const group of demoGroups) {
    const assigned = current.envelopes[group.id] ?? 0;
    const children = demoGroups
      .filter((child) => child.parent_id === group.id)
      .reduce((sum, child) => sum + (current.envelopes[child.id] ?? 0), 0);
    const direct = demoMembers
      .filter((member) => member.node === group.id)
      .map((member) => member.user_id)
      .sort();
    const manual = direct.filter((user) => user in current.overrides);
    const automatic = direct.filter((user) => !(user in current.overrides));
    let available =
      assigned -
      children -
      manual.reduce((sum, user) => sum + current.overrides[user], 0);
    if (available < 0) {
      rows[group.id] = {
        assigned,
        allocated: null,
        remainder: null,
        shortfall: -available,
        users: Object.fromEntries(
          direct.map((user) => [user, current.overrides[user] ?? null]),
        ),
      };
      continue;
    }
    const share = automatic.length
      ? Math.floor(available / automatic.length)
      : 0;
    available -= share * automatic.length;
    rows[group.id] = {
      assigned,
      allocated: assigned - available,
      remainder: available,
      shortfall: 0,
      users: Object.fromEntries(
        direct.map((user) => [user, current.overrides[user] ?? share]),
      ),
    };
  }
  return rows;
}

/** The allowance a member's key gets: the share, never above the cap. */
function displayed(current: State, groupId: string, value: number | null) {
  const cap = perUserOf(current, groupId);
  if (!(current.envelopes[groupId] ?? 0)) return cap;
  if (value === null) return null;
  return cap === null ? value / 100 : Math.min(value / 100, cap);
}

export function budgetView(actor: BudgetActor): BudgetView {
  const rows = allocate(state);
  const groups: BudgetGroup[] = demoGroups
    .filter((group) => actor.allows(group.id))
    .map((group) => {
      const row = rows[group.id];
      const cents = (value: number | null) =>
        value === null ? null : value / 100;
      return {
        id: group.id,
        name: group.name,
        path: group.path,
        parent_id: group.parent_id,
        duration: group.duration,
        assigned: row.assigned / 100,
        allocated: cents(row.allocated),
        reserved: 0,
        remainder: cents(row.remainder),
        allocation_error: row.shortfall ? ALLOCATION_ERROR : null,
        used: null,
        remaining: null,
        can_edit_envelope:
          actor.admin || (!!group.parent_id && actor.allows(group.parent_id)),
        per_user: perUserOf(state, group.id),
        per_user_config: group.per_user,
        per_user_override:
          group.id in state.perUser ? state.perUser[group.id] : null,
        can_edit_per_user: actor.admin,
        users: Object.entries(row.users).map(([userId, value]) => ({
          user_id: userId,
          email:
            demoMembers.find((member) => member.user_id === userId)?.email ??
            "",
          allocation: displayed(state, group.id, value),
          override:
            userId in state.overrides ? state.overrides[userId] / 100 : null,
          mode:
            userId in state.overrides
              ? "manual"
              : state.envelopes[group.id]
                ? "automatic"
                : "fixed",
          used: null,
          remaining: null,
          can_edit: actor.admin || userId !== actor.userId,
        })),
      };
    });
  return {
    revision: state.revision,
    mode: "preview",
    applied: false,
    pending: false,
    capability: {
      supported: false,
      version: null,
      reasons: ["Demo budgets are synthetic and never cap real keys."],
    },
    groups,
  };
}

type Result = { status: number; body: unknown };
const fail = (status: number, detail: string): Result => ({
  status,
  body: { detail },
});

/** Applies a change unless it worsens a deficit or raises the actor's own share. */
function edit(
  actor: BudgetActor,
  revision: unknown,
  change: (next: State) => Result | void,
): Result {
  if (revision !== state.revision)
    return fail(409, "Budget revision changed; reload and try again");
  const next: State = {
    ...state,
    envelopes: { ...state.envelopes },
    overrides: { ...state.overrides },
    perUser: { ...state.perUser },
  };
  const refused = change(next);
  if (refused) return refused;
  const before = allocate(state);
  const after = allocate(next);
  if (
    Object.keys(after).some((id) => after[id].shortfall > before[id].shortfall)
  )
    return fail(409, ALLOCATION_ERROR);
  const own = demoMembers.find((member) => member.user_id === actor.userId);
  if (!actor.admin && own) {
    const was = before[own.node].users[actor.userId] ?? 0;
    const now = after[own.node].users[actor.userId] ?? 0;
    if (now > was)
      return fail(
        403,
        "A parent or system administrator must increase your personal allowance",
      );
  }
  state = { ...next, revision: state.revision + 1 };
  return { status: 200, body: budgetView(actor) };
}

export function setEnvelope(
  actor: BudgetActor,
  groupId: string,
  payload: Record<string, unknown>,
): Result {
  const group = demoGroups.find((item) => item.id === groupId);
  if (!group || !actor.allows(groupId))
    return fail(404, "Organization group not found");
  if (!actor.admin && !(group.parent_id && actor.allows(group.parent_id)))
    return fail(
      403,
      "Only a parent or system administrator can change this team's assigned budget; redistribute it among members or child teams",
    );
  const amount = toCents(payload.amount);
  if (!Number.isFinite(amount) || amount < 0)
    return fail(422, "Enter a budget of zero or more");
  return edit(actor, payload.revision, (next) => {
    next.envelopes[groupId] = amount;
  });
}

export function setOverride(
  actor: BudgetActor,
  groupId: string,
  userId: string,
  payload: Record<string, unknown>,
): Result {
  if (!actor.allows(groupId)) return fail(404, "Organization group not found");
  const amount = payload.amount == null ? null : toCents(payload.amount);
  if (amount !== null && (!Number.isFinite(amount) || amount < 0))
    return fail(422, "Enter an allowance of zero or more");
  return edit(actor, payload.revision, (next) => {
    const member = demoMembers.find((item) => item.user_id === userId);
    if (member?.node !== groupId)
      return fail(404, "Direct organization member not found");
    if (amount === null) delete next.overrides[userId];
    else next.overrides[userId] = amount;
  });
}

export function setPerUser(
  actor: BudgetActor,
  groupId: string,
  payload: Record<string, unknown>,
): Result {
  if (!actor.admin) return fail(403, "System administrator access required");
  const group = demoGroups.find((item) => item.id === groupId);
  if (!group) return fail(404, "Organization group not found");
  const amount = payload.amount == null ? null : Number(payload.amount);
  if (amount !== null && (!Number.isFinite(amount) || amount < 0))
    return fail(422, "Enter a limit of zero or more");
  if (amount === null) delete state.perUser[groupId];
  else state.perUser[groupId] = amount;
  const limit: PerUserLimit = {
    node_id: groupId,
    per_user: perUserOf(state, groupId),
    per_user_config: group.per_user,
    per_user_override: amount,
  };
  return { status: 200, body: limit };
}
