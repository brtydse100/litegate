import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import BulkKeyEditor from "./BulkKeyEditor";

vi.mock("../api/client", () => ({
  api: {
    listAllKeys: vi.fn(),
    listAllKeyIdentifiers: vi.fn(),
    bulkUpdateKeys: vi.fn(),
    resetKeySpend: vi.fn(),
    getOperationLimit: vi.fn(),
    revealKey: vi.fn(),
    listModels: vi.fn(),
  },
}));

const keys = [
  {
    token: "key-1",
    key_alias: "Alice",
    spend: 1,
    models: [],
    user_id: "alice",
  },
  { token: "key-2", key_alias: "Bob", spend: 2, models: [], user_id: "bob" },
];

function renderEditor(saveApiKeysInDb = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <BulkKeyEditor expanded saveApiKeysInDb={saveApiKeysInDb} />
    </QueryClientProvider>,
  );
}

describe("BulkKeyEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listModels).mockResolvedValue({
      models: ["model-a", "model-b"],
    });
    vi.mocked(api.getOperationLimit).mockResolvedValue({
      limit: 5,
      remaining: 5,
      retry_after: 0,
    });
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys,
      page: 1,
      size: 25,
      total: 2,
      total_pages: 1,
    });
    vi.mocked(api.listAllKeyIdentifiers).mockResolvedValue({
      keys: ["key-1", "key-2"],
      total: 2,
    });
  });

  it("hides settings until a key is selected and opens them for a new selection", async () => {
    renderEditor();
    const alice = await screen.findByRole("checkbox", { name: "Select Alice" });
    expect(
      screen.queryByText("Choose settings to change"),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Alias")).not.toBeInTheDocument();
    fireEvent.click(alice);
    expect(screen.getByLabelText("Alias")).toBeVisible();
    fireEvent.click(screen.getByText("Choose settings to change"));
    expect(screen.getByLabelText("Alias")).not.toBeVisible();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Bob" }));
    expect(screen.getByLabelText("Alias")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(
      screen.queryByText("Choose settings to change"),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Alias")).not.toBeInTheDocument();
  });

  it("shows saved settings without submitting them as changes", async () => {
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys: [
        {
          ...keys[0],
          max_budget: 75,
          budget_duration: "30d",
          models: ["model-a"],
          blocked: true,
          tpm_limit: 500,
          rpm_limit: 125,
        },
      ],
      page: 1,
      size: 25,
      total: 1,
      total_pages: 1,
    });
    vi.mocked(api.bulkUpdateKeys).mockResolvedValue({
      updated: 1,
      failed: 0,
      results: [{ key: "key-1", updated: true }],
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Select Alice" }),
    );
    const current = screen.getByRole("region", {
      name: "Current key settings",
    });
    expect(within(current).getByText("$75")).toBeVisible();
    expect(within(current).getByText("30d")).toBeVisible();
    expect(within(current).getByText("Blocked")).toBeVisible();
    expect(screen.getByLabelText("Alias")).toHaveValue("Alice");
    expect(screen.getByLabelText("Maximum budget")).toHaveValue(75);
    expect(screen.getByLabelText("Alias")).toHaveAttribute(
      "placeholder",
      "Alice",
    );
    expect(screen.getByLabelText("Maximum budget")).toHaveAttribute(
      "placeholder",
      "75",
    );
    expect(screen.getByLabelText("Budget reset")).toHaveAttribute(
      "placeholder",
      "30d",
    );
    expect(screen.getByLabelText("TPM limit")).toHaveAttribute(
      "placeholder",
      "500",
    );
    expect(screen.getByLabelText("RPM limit")).toHaveAttribute(
      "placeholder",
      "125",
    );
    fireEvent.change(screen.getByLabelText("Maximum budget"), {
      target: { value: "" },
    });
    expect(screen.getByLabelText("Maximum budget")).toHaveValue(null);
    expect(screen.getByLabelText("Maximum budget")).toHaveAttribute(
      "placeholder",
      "75",
    );
    expect(screen.getByLabelText("Budget reset")).toHaveValue("30d");
    expect(screen.getByRole("checkbox", { name: "model-a" })).toBeChecked();
    expect(
      screen.queryByRole("textbox", { name: "Allowed models" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Blocked state")).toHaveValue("true");
    fireEvent.change(screen.getByLabelText("RPM limit"), {
      target: { value: "100" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 1 key" }),
    );
    await waitFor(() =>
      expect(api.bulkUpdateKeys).toHaveBeenCalledWith(["key-1"], {
        rpm_limit: 100,
      }),
    );
  });

  it("prefills shared values and marks different selected-key values as mixed", async () => {
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys: [
        {
          ...keys[0],
          max_budget: 75,
          rpm_limit: 100,
          models: ["model-a", "model-b"],
          blocked: false,
        },
        {
          ...keys[1],
          max_budget: 75,
          rpm_limit: 200,
          models: ["model-b", "model-a"],
          blocked: false,
        },
      ],
      page: 1,
      size: 25,
      total: 2,
      total_pages: 1,
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select page (2)" }),
    );
    expect(screen.getByLabelText("Maximum budget")).toHaveValue(75);
    expect(screen.getByLabelText("Blocked state")).toHaveValue("false");
    expect(screen.getByRole("checkbox", { name: "model-a" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "model-b" })).toBeChecked();
    expect(screen.getByLabelText("Alias")).toHaveAttribute(
      "placeholder",
      "Mixed values",
    );
    expect(screen.getByLabelText("RPM limit")).toHaveValue(null);
    expect(screen.getByLabelText("RPM limit")).toHaveAttribute(
      "placeholder",
      "Mixed values",
    );
  });

  it("resets drafts when the selected keys change instead of carrying one key's edits to another", async () => {
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys: [
        { ...keys[0], max_budget: 75 },
        { ...keys[1], max_budget: 150 },
      ],
      page: 1,
      size: 25,
      total: 2,
      total_pages: 1,
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Select Alice" }),
    );
    fireEvent.change(screen.getByLabelText("Maximum budget"), {
      target: { value: "500" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "Deselect Alice" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Bob" }));
    expect(screen.getByLabelText("Alias")).toHaveValue("Bob");
    expect(screen.getByLabelText("Maximum budget")).toHaveValue(150);
  });

  it("does not submit saved values just because a key was selected", async () => {
    renderEditor();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Select Alice" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 1 key" }),
    );
    expect(
      await screen.findByText("Choose at least one setting to change."),
    ).toBeVisible();
    expect(api.bulkUpdateKeys).not.toHaveBeenCalled();
  });

  it("does not imply that keys on other pages share the displayed settings", async () => {
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys: [keys[0]],
      page: 1,
      size: 25,
      total: 2,
      total_pages: 2,
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select all keys (2)" }),
    );
    const current = await screen.findByRole("region", {
      name: "Current key settings",
    });
    expect(
      within(current).getByText(/1 selected key is on another page/),
    ).toBeVisible();
    expect(screen.getByLabelText("Alias")).toHaveValue("");
    expect(screen.getByLabelText("Alias")).toHaveAttribute(
      "placeholder",
      "Current values unavailable",
    );
  });

  it("offers model choices and explicitly requests removal of separate user caps", async () => {
    vi.mocked(api.bulkUpdateKeys).mockResolvedValue({
      updated: 1,
      failed: 0,
      results: [{ key: "key-1", updated: true }],
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Select Alice" }),
    );
    fireEvent.click(await screen.findByRole("checkbox", { name: "model-b" }));
    expect(screen.getByRole("checkbox", { name: "model-b" })).toBeChecked();
    fireEvent.change(screen.getByLabelText("Maximum budget"), {
      target: { value: "150" },
    });
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Use key budget as the individual allowance",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 1 key" }),
    );
    await waitFor(() =>
      expect(api.bulkUpdateKeys).toHaveBeenCalledWith(
        ["key-1"],
        { max_budget: 150, models: ["model-b"] },
        true,
      ),
    );
  });

  it("does not turn an empty checkbox selection into unrestricted model access", async () => {
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys: [{ ...keys[0], models: ["model-a"] }],
      page: 1,
      size: 25,
      total: 1,
      total_pages: 1,
    });
    vi.mocked(api.bulkUpdateKeys).mockResolvedValue({
      updated: 1,
      failed: 0,
      results: [{ key: "key-1", updated: true }],
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Select Alice" }),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "model-a" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 1 key" }),
    );
    expect(
      await screen.findAllByText(
        "Select at least one model or allow all models.",
      ),
    ).not.toHaveLength(0);
    expect(api.bulkUpdateKeys).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "All allowed models" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 1 key" }),
    );
    await waitFor(() =>
      expect(api.bulkUpdateKeys).toHaveBeenCalledWith(["key-1"], {
        models: [],
      }),
    );
  });

  it("sends catalog model names as array entries without splitting their punctuation", async () => {
    vi.mocked(api.listModels).mockResolvedValue({
      models: ["vendor/model,variant"],
    });
    vi.mocked(api.bulkUpdateKeys).mockResolvedValue({
      updated: 1,
      failed: 0,
      results: [{ key: "key-1", updated: true }],
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Select Alice" }),
    );
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "vendor/model,variant" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 1 key" }),
    );
    await waitFor(() =>
      expect(api.bulkUpdateKeys).toHaveBeenCalledWith(["key-1"], {
        models: ["vendor/model,variant"],
      }),
    );
  });

  it("leaves different model policies untouched when only another bulk setting is edited", async () => {
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys: [
        { ...keys[0], models: ["model-a"] },
        { ...keys[1], models: ["model-b"] },
      ],
      page: 1,
      size: 25,
      total: 2,
      total_pages: 1,
    });
    vi.mocked(api.bulkUpdateKeys).mockResolvedValue({
      updated: 2,
      failed: 0,
      results: [
        { key: "key-1", updated: true },
        { key: "key-2", updated: true },
      ],
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select page (2)" }),
    );
    expect(
      screen.getByRole("checkbox", { name: "All allowed models" }),
    ).not.toBeChecked();
    fireEvent.change(screen.getByLabelText("RPM limit"), {
      target: { value: "100" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 2 keys" }),
    );
    await waitFor(() =>
      expect(api.bulkUpdateKeys).toHaveBeenCalledWith(["key-1", "key-2"], {
        rpm_limit: 100,
      }),
    );
  });

  it("lets administrators reveal a stored key from the list", async () => {
    vi.mocked(api.listAllKeys).mockResolvedValue({
      keys: [{ ...keys[0], secret_available: true }, keys[1]],
      page: 1,
      size: 25,
      total: 2,
      total_pages: 1,
    });
    vi.mocked(api.revealKey).mockResolvedValue({ key: "sk-synthetic-admin" });
    renderEditor(true);
    fireEvent.click(
      await screen.findByRole("button", { name: "Show API key" }),
    );
    expect(await screen.findByText("sk-synthetic-admin")).toBeVisible();
    expect(api.revealKey).toHaveBeenCalledWith("key-1");
    expect(
      screen.getByRole("checkbox", { name: "Select Alice" }),
    ).not.toBeChecked();
  });

  it("migrates an existing allowance without edits and preserves that choice on retry", async () => {
    vi.mocked(api.bulkUpdateKeys)
      .mockResolvedValueOnce({
        updated: 0,
        failed: 1,
        results: [{ key: "key-1", updated: false, error: "Retry migration" }],
      })
      .mockResolvedValueOnce({
        updated: 1,
        failed: 0,
        results: [{ key: "key-1", updated: true }],
      });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Select Alice" }),
    );
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Use key budget as the individual allowance",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 1 key" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Retry failed" }),
    );
    await waitFor(() => expect(api.bulkUpdateKeys).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.bulkUpdateKeys).mock.calls.slice(-2)).toEqual([
      [["key-1"], {}, true],
      [["key-1"], {}, true],
    ]);
  });

  it("selects every result, not only the visible page", async () => {
    renderEditor();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select all keys (2)" }),
    );
    expect((await screen.findAllByText("2 selected")).length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByRole("button", { name: "Deselect all (2)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Apply settings to 2 keys" }),
    ).toBeInTheDocument();
  });

  it("keeps failed keys selected for retry and export", async () => {
    vi.mocked(api.bulkUpdateKeys).mockResolvedValue({
      updated: 1,
      failed: 1,
      results: [
        { key: "key-1", updated: true },
        { key: "key-2", updated: false, error: "LiteLLM rejected the policy" },
      ],
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select all keys (2)" }),
    );
    await screen.findByRole("button", { name: "Deselect all (2)" });
    fireEvent.change(screen.getByLabelText("RPM limit"), {
      target: { value: "100" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Apply settings to 2 keys" }),
    );
    expect(
      await screen.findByRole("button", { name: "Retry failed" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Download failures" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText("1 selected").length).toBeGreaterThan(0),
    );
  });

  it("resets multiple selected keys and keeps failures selected", async () => {
    vi.mocked(api.resetKeySpend).mockResolvedValue({
      reset: 1,
      failed: 1,
      results: [
        { key: "key-1", reset: true },
        { key: "key-2", reset: false, error: "LiteLLM rejected the reset" },
      ],
    });
    renderEditor();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select all keys (2)" }),
    );
    await screen.findByRole("button", { name: "Deselect all (2)" });
    fireEvent.click(
      screen.getByRole("button", { name: "Reset spend for 2 keys" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Reset spend for 2 keys?" }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Reset spend to zero" }),
    );

    await waitFor(() =>
      expect(api.resetKeySpend).toHaveBeenCalledWith(["key-1", "key-2"]),
    );
    expect(await screen.findByText("1 reset, 1 failed.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry failed" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Download failures" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText("1 selected").length).toBeGreaterThan(0),
    );
  });
});
