import { beforeEach, expect, it } from "vitest";
import {
  budgetView,
  resetDemoBudgets,
  setEnvelope,
  setOverride,
  setPerUser,
  type BudgetActor,
} from "./budgets";

const within = (root: string[]) => (id: string) =>
  root.includes(id) ||
  (root.includes("infrastructure") && ["platform", "cloud"].includes(id));
const admin: BudgetActor = { admin: true, userId: "admin", allows: () => true };
const teamsOwner: BudgetActor = {
  admin: false,
  userId: "priya",
  allows: within(["infrastructure"]),
};
const peopleOwner: BudgetActor = {
  admin: false,
  userId: "demo-admin",
  allows: within(["platform"]),
};
const group = (actor: BudgetActor, id: string) =>
  budgetView(actor).groups.find((item) => item.id === id)!;

beforeEach(resetDemoBudgets);

it("shares a team's budget equally, capped by the per-user limit", () => {
  const platform = group(admin, "platform");
  expect(platform.assigned).toBe(250);
  expect(platform.users.map((user) => user.allocation)).toEqual([
    83.33, 83.33, 83.33,
  ]);
  expect(
    setOverride(admin, "platform", "noa", { revision: 1, amount: 150 }),
  ).toMatchObject({ status: 200 });
  const noa = group(admin, "platform").users.find(
    (user) => user.user_id === "noa",
  )!;
  expect(noa).toMatchObject({ mode: "manual", override: 150, allocation: 100 });
});

it("lets owners split inside their scope but not change their own total", () => {
  expect(budgetView(teamsOwner).groups.map((item) => item.id)).toEqual([
    "infrastructure",
    "platform",
    "cloud",
  ]);
  expect(group(teamsOwner, "infrastructure").can_edit_envelope).toBe(false);
  expect(group(teamsOwner, "platform").can_edit_envelope).toBe(true);
  expect(
    setEnvelope(teamsOwner, "infrastructure", { revision: 1, amount: 900 })
      .status,
  ).toBe(403);
  // More than Infrastructure was given is refused, a fair split is saved.
  expect(
    setEnvelope(teamsOwner, "platform", { revision: 1, amount: 400 }).status,
  ).toBe(409);
  expect(
    setEnvelope(teamsOwner, "platform", { revision: 1, amount: 270 }).status,
  ).toBe(200);
  expect(group(teamsOwner, "platform").assigned).toBe(270);
  expect(
    setEnvelope(teamsOwner, "marketing", { revision: 2, amount: 1 }).status,
  ).toBe(404);
});

it("never lets an owner raise their own allowance or set per-user limits", () => {
  const own = group(peopleOwner, "platform").users.find(
    (user) => user.user_id === "demo-admin",
  )!;
  expect(own.can_edit).toBe(false);
  expect(group(peopleOwner, "platform").can_edit_per_user).toBe(false);
  // Lowering a teammate would grow the owner's own equal share.
  expect(
    setOverride(peopleOwner, "platform", "noa", { revision: 1, amount: 10 }),
  ).toMatchObject({ status: 403 });
  expect(
    setOverride(peopleOwner, "platform", "noa", { revision: 1, amount: 90 })
      .status,
  ).toBe(200);
  expect(setPerUser(peopleOwner, "platform", { amount: 500 }).status).toBe(403);
  expect(setPerUser(admin, "platform", { amount: 60 }).status).toBe(200);
});

it("rejects edits against an old revision", () => {
  expect(
    setOverride(admin, "platform", "noa", { revision: 1, amount: 50 }).status,
  ).toBe(200);
  expect(
    setOverride(admin, "platform", "lee", { revision: 1, amount: 50 }).status,
  ).toBe(409);
});
