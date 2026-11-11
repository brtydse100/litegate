import { createRef } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import AdvancedPolicySettings, {
  type AdvancedPolicyHandle,
} from "./AdvancedPolicySettings";

vi.mock("../api/client", () => ({ api: { policySchemas: vi.fn() } }));
const properties = {
  max_budget: { type: "number" },
  new_limit: { type: "integer", minimum: 1, maximum: 10 },
  new_flag: { type: "boolean" },
  object_permission: {
    type: "object",
    properties: { mcp_servers: { type: "array", items: { type: "string" } } },
  },
  model_max_budget: { type: "object" },
  member_budget: { anyOf: [{ type: "number", minimum: 0 }, { type: "null" }] },
  strategy: { type: "string", enum: ["fast", "safe"] },
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.policySchemas).mockResolvedValue({
    available: true,
    schemas: { team_update: { properties } },
  });
});

it("prefills advertised metadata-backed settings without exposing unrelated metadata", async () => {
  setup({ metadata: { new_limit: 4, secret: "never-display" } });
  await open();
  fireEvent.click(screen.getByLabelText("Edit new_limit"));
  expect(screen.getByLabelText("new_limit")).toHaveValue(4);
  expect(screen.queryByDisplayValue("never-display")).not.toBeInTheDocument();
});

it("prefills only editable MCP permission properties from expanded upstream records", async () => {
  setup({
    object_permission: {
      mcp_servers: ["local"],
      object_permission_id: "internal-id",
    },
  });
  await open();
  fireEvent.click(screen.getByLabelText("Edit object_permission"));
  expect(screen.getByLabelText("object_permission")).toHaveValue(
    '{"mcp_servers":["local"]}',
  );
});
function setup(current?: Record<string, unknown>) {
  const ref = createRef<AdvancedPolicyHandle>();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AdvancedPolicySettings
        ref={ref}
        operation="team_update"
        excludedFields={["max_budget"]}
        current={current}
      />
    </QueryClientProvider>,
  );
  return { ref, client };
}
async function open() {
  fireEvent.click(screen.getByText("Advanced settings"));
  await screen.findByLabelText("Edit new_limit");
}
it("loads only on demand and includes future fields without submitting saved/default values", async () => {
  const { ref } = setup({
    new_limit: 3,
    object_permission: { mcp_servers: ["existing"] },
  });
  expect(api.policySchemas).not.toHaveBeenCalled();
  await open();
  expect(screen.queryByLabelText("Edit max_budget")).not.toBeInTheDocument();
  expect(ref.current!.read()).toEqual({});
  fireEvent.click(screen.getByLabelText("Edit new_limit"));
  expect(screen.getByLabelText("new_limit")).toHaveValue(3);
  fireEvent.change(screen.getByLabelText("new_limit"), {
    target: { value: "4" },
  });
  fireEvent.click(screen.getByLabelText("Edit new_flag"));
  fireEvent.change(screen.getByLabelText("new_flag"), {
    target: { value: "false" },
  });
  expect(ref.current!.read()).toEqual({ new_limit: 4, new_flag: false });
});
it("validates bounds, enum, nested MCP JSON, and explicit nullable clearing", async () => {
  const { ref } = setup();
  await open();
  fireEvent.click(screen.getByLabelText("Edit new_limit"));
  fireEvent.change(screen.getByLabelText("new_limit"), {
    target: { value: "11" },
  });
  expect(() => ref.current!.read()).toThrow("new_limit");
  fireEvent.change(screen.getByLabelText("new_limit"), {
    target: { value: "5" },
  });
  fireEvent.click(screen.getByLabelText("Edit object_permission"));
  fireEvent.change(screen.getByLabelText("object_permission"), {
    target: { value: '{"mcp_servers":[5]}' },
  });
  expect(() => ref.current!.read()).toThrow("mcp_servers");
  fireEvent.change(screen.getByLabelText("object_permission"), {
    target: { value: '{"mcp_servers":["local"]}' },
  });
  fireEvent.click(screen.getByLabelText("Edit member_budget"));
  fireEvent.click(screen.getByLabelText("Clear member_budget"));
  expect(screen.queryByLabelText("Clear new_limit")).not.toBeInTheDocument();
  expect(ref.current!.read()).toEqual({
    new_limit: 5,
    object_permission: { mcp_servers: ["local"] },
    member_budget: null,
  });
});
it("provides retry when discovery is unavailable and leaves familiar settings usable", async () => {
  vi.mocked(api.policySchemas).mockResolvedValue({
    available: false,
    schemas: {},
    detail: "unavailable",
  });
  const { ref } = setup();
  fireEvent.click(screen.getByText("Advanced settings"));
  expect(
    await screen.findByRole("button", { name: "Retry discovery" }),
  ).toBeVisible();
  expect(ref.current!.read()).toEqual({});
  fireEvent.click(screen.getByRole("button", { name: "Retry discovery" }));
  await waitFor(() => expect(api.policySchemas).toHaveBeenCalledTimes(2));
});

it("rejects malformed JSON and clears the visible error when corrected", async () => {
  const { ref } = setup();
  await open();
  fireEvent.click(screen.getByLabelText("Edit object_permission"));
  fireEvent.change(screen.getByLabelText("object_permission"), {
    target: { value: "{" },
  });
  act(() => {
    expect(() => ref.current!.read()).toThrow("valid JSON");
  });
  expect(screen.getByRole("alert")).toHaveTextContent("valid JSON");
  fireEvent.change(screen.getByLabelText("object_permission"), {
    target: { value: "{}" },
  });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(ref.current!.read()).toEqual({ object_permission: {} });
});

it("offers enum choices and submits none until the administrator selects a value", async () => {
  const { ref } = setup();
  await open();
  fireEvent.click(screen.getByLabelText("Edit strategy"));
  expect(() => ref.current!.read()).toThrow("choose a value");
  fireEvent.change(screen.getByLabelText("strategy"), {
    target: { value: '"safe"' },
  });
  expect(ref.current!.read()).toEqual({ strategy: "safe" });
  fireEvent.click(screen.getByLabelText("Edit strategy"));
  expect(ref.current!.read()).toEqual({});
});

it("discovers fields introduced by a later LiteLLM version on refresh", async () => {
  const { client } = setup();
  await open();
  vi.mocked(api.policySchemas).mockResolvedValue({
    available: true,
    schemas: {
      team_update: {
        properties: {
          ...properties,
          future_setting: { type: "number" },
          api_key: { type: "string" },
          password: { type: "string" },
          read_only: { type: "string", readOnly: true },
        },
      },
    },
  });
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["policy-schemas"] });
  });
  expect(await screen.findByLabelText("Edit future_setting")).toBeVisible();
  expect(screen.queryByLabelText("Edit api_key")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Edit password")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Edit read_only")).not.toBeInTheDocument();
});
