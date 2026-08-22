import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import AdminStatus from "./AdminStatus";

vi.mock("../api/client", () => ({
  api: {
    getSystemStatus: vi.fn(),
    listAuditEvents: vi.fn(),
  },
}));

function renderStatus() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AdminStatus />
    </QueryClientProvider>,
  );
}

describe("administrator status contract", () => {
  beforeEach(() => {
    vi.mocked(api.listAuditEvents).mockResolvedValue({ events: [] });
  });

  it("still renders when an older backend omits newly added optional fields", async () => {
    vi.mocked(api.getSystemStatus).mockResolvedValue({
      ready: true,
      dependencies: {
        litellm: { ok: true, detail: "Connected" },
        database: { ok: true, detail: "Writable" },
      },
      storage_mode: "sqlite-single-replica",
    });

    renderStatus();

    expect(await screen.findByText("LiteGate is ready to serve requests.", { exact: false })).toBeVisible();
    expect(screen.queryByText("Deployment security warnings")).not.toBeInTheDocument();
  });

  it("shows every actionable security warning returned by the backend", async () => {
    vi.mocked(api.getSystemStatus).mockResolvedValue({
      ready: true,
      dependencies: {
        litellm: { ok: true, detail: "Connected" },
        database: { ok: true, detail: "Writable" },
      },
      storage_mode: "sqlite-single-replica",
      security_warnings: ["Use HTTPS.", "Rotate the bootstrap password."],
    });

    renderStatus();

    expect(await screen.findByText("Deployment security warnings")).toBeVisible();
    expect(screen.getByText("Use HTTPS.")).toBeVisible();
    expect(screen.getByText("Rotate the bootstrap password.")).toBeVisible();
  });
});
