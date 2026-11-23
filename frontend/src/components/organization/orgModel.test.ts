import { describe, expect, it } from "vitest";
import { limitOrigin, plural, reached, shortMoney } from "./orgModel";

describe("limitOrigin", () => {
  const parent = { name: "Engineering", per_user: 50 };

  it("calls a limit set on a sub-group an override", () => {
    expect(
      limitOrigin({ id: "apps", budget_source: "apps", per_user: 10 }, parent),
    ).toEqual({ tag: "override", description: "Overrides Engineering ($50)" });
  });

  it("calls a limit set on a top-level group set here", () => {
    expect(
      limitOrigin({ id: "eng", budget_source: "eng", per_user: 50 }).tag,
    ).toBe("set here");
  });

  it("names a visible source group", () => {
    expect(
      limitOrigin({ id: "apps", budget_source: "eng", per_user: 50 }, parent, {
        name: "Engineering",
      }).description,
    ).toBe("Inherited from Engineering");
  });

  it("never claims an override when no limit exists anywhere", () => {
    expect(
      limitOrigin({ id: "apps", budget_source: null, per_user: null }, parent),
    ).toEqual({
      tag: "",
      description: "No limit is set on this group or above it",
    });
  });

  it("does not name a source outside the viewer's scope", () => {
    expect(
      limitOrigin({ id: "apps", budget_source: null, per_user: 50 }, parent),
    ).toEqual({
      tag: "inherited",
      description: "Inherited from a group outside your view",
    });
  });
});

describe("reached", () => {
  it("compares unrounded spend with the threshold", () => {
    expect(reached(79.6, 100, 80)).toBe(false);
    expect(reached(80, 100, 80)).toBe(true);
    expect(reached(5, null, 80)).toBe(false);
    expect(reached(null, 100, 80)).toBe(false);
  });
});

describe("shortMoney", () => {
  it("puts the sign before the currency symbol", () => {
    expect(shortMoney(-5)).toBe("-$5");
    expect(shortMoney(1200)).toBe("$1,200");
    expect(shortMoney(null)).toBe("—");
  });
});

describe("plural", () => {
  it("pluralises level names", () => {
    expect(plural(2, "Branch")).toBe("2 branches");
    expect(plural(1, "Branch")).toBe("1 branch");
    expect(plural(3, "Team")).toBe("3 teams");
    expect(plural(2, "Person")).toBe("2 people");
  });
});
