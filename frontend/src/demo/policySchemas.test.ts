import { expect, it } from "vitest";
import { demoAdvancedSettings, demoPolicySchemas } from "./policySchemas";

it("provides synthetic MCP and member-default schemas without claiming member per-model support", () => {
  const team = demoPolicySchemas.schemas.team_update?.properties as Record<
    string,
    unknown
  >;
  expect(team.object_permission).toBeDefined();
  expect(team.mcp_rpm_limit).toBeDefined();
  expect(team.team_member_budget).toBeDefined();
  expect(team.model_max_budget).toBeUndefined();
});

it("applies opted-in Advanced values to the same shape returned by the real API", () => {
  expect(
    demoAdvancedSettings({
      team_alias: "Platform",
      advanced_settings: {
        team_member_budget: 25,
        mcp_rpm_limit: { "synthetic-mcp": 10 },
      },
    }),
  ).toEqual({
    team_alias: "Platform",
    team_member_budget: 25,
    mcp_rpm_limit: { "synthetic-mcp": 10 },
  });
  expect(demoAdvancedSettings({ team_alias: "Platform" })).toEqual({
    team_alias: "Platform",
  });
});
