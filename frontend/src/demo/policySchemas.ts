import type { PolicySchemaResponse } from "../types";

// A small synthetic schema catalog. Production discovers the connected proxy.
const shared = {
  mcp_rpm_limit: {
    title: "MCP requests per minute",
    description: "Rate limits keyed by synthetic MCP server name.",
    anyOf: [
      { type: "object", additionalProperties: { type: "integer", minimum: 0 } },
      { type: "null" },
    ],
  },
  object_permission: {
    description: "Synthetic MCP server and tool access.",
    anyOf: [
      {
        type: "object",
        properties: {
          mcp_servers: { type: "array", items: { type: "string" } },
          mcp_tool_permissions: {
            type: "object",
            additionalProperties: { type: "array", items: { type: "string" } },
          },
        },
      },
      { type: "null" },
    ],
  },
  model_rpm_limit: {
    description: "Requests per minute for each model alias.",
    anyOf: [
      { type: "object", additionalProperties: { type: "integer", minimum: 0 } },
      { type: "null" },
    ],
  },
};
const team = {
  type: "object",
  properties: {
    ...shared,
    team_member_budget: {
      description: "Default overall allowance for each team member.",
      anyOf: [{ type: "number", minimum: 0 }, { type: "null" }],
    },
    team_member_budget_duration: {
      description: "Reset interval for the default member allowance.",
      anyOf: [{ type: "string" }, { type: "null" }],
    },
  },
};

export const demoPolicySchemas: PolicySchemaResponse = {
  available: true,
  schemas: {
    key_update: {
      type: "object",
      properties: {
        ...shared,
        max_parallel_requests: {
          description: "Concurrent requests allowed for this key.",
          anyOf: [{ type: "integer", minimum: 1 }, { type: "null" }],
        },
      },
    },
    team_create: team,
    team_update: team,
  },
};

export function demoAdvancedSettings(payload: Record<string, unknown>) {
  const { advanced_settings, ...core } = payload;
  return {
    ...core,
    ...(advanced_settings &&
    typeof advanced_settings === "object" &&
    !Array.isArray(advanced_settings)
      ? advanced_settings
      : {}),
  };
}
