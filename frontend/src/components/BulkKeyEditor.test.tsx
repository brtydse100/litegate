import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import BulkKeyEditor from "./BulkKeyEditor";

vi.mock("../api/client", () => ({
  api: {
    listAllKeys: vi.fn(),
    listAllKeyIdentifiers: vi.fn(),
    bulkUpdateKeys: vi.fn(),
    getOperationLimit: vi.fn(),
  },
}));

const keys = [
  { token: "key-1", key_alias: "Alice", spend: 1, models: [], user_id: "alice" },
  { token: "key-2", key_alias: "Bob", spend: 2, models: [], user_id: "bob" },
];

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><BulkKeyEditor expanded /></QueryClientProvider>);
}

describe("BulkKeyEditor", () => {
  beforeEach(() => {
    vi.mocked(api.getOperationLimit).mockResolvedValue({ limit: 5, remaining: 5, retry_after: 0 });
    vi.mocked(api.listAllKeys).mockResolvedValue({ keys, page: 1, size: 25, total: 2, total_pages: 1 });
    vi.mocked(api.listAllKeyIdentifiers).mockResolvedValue({ keys: ["key-1", "key-2"], total: 2 });
  });

  it("selects every result, not only the visible page", async () => {
    renderEditor();
    fireEvent.click(await screen.findByRole("button", { name: "Select all keys (2)" }));
    expect((await screen.findAllByText("2 selected")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Deselect all (2)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply settings to 2 keys" })).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: "Select all keys (2)" }));
    await screen.findByRole("button", { name: "Deselect all (2)" });
    fireEvent.change(screen.getByLabelText("RPM limit"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply settings to 2 keys" }));
    expect(await screen.findByRole("button", { name: "Retry failed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download failures" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("1 selected").length).toBeGreaterThan(0));
  });
});
