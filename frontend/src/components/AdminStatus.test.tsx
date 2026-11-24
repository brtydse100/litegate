import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import AdminAudit from "./AdminAudit";
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
      <MemoryRouter>
        <AdminStatus />
      </MemoryRouter>
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

    expect(
      await screen.findByText("LiteGate is ready to serve requests.", {
        exact: false,
      }),
    ).toBeVisible();
    expect(
      screen.queryByText("Deployment security warnings"),
    ).not.toBeInTheDocument();
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

    expect(
      await screen.findByText("Deployment security warnings"),
    ).toBeVisible();
    expect(screen.getByText("Use HTTPS.")).toBeVisible();
    expect(screen.getByText("Rotate the bootstrap password.")).toBeVisible();
  });
});

describe("separate Status and Audit log pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getSystemStatus).mockResolvedValue({
      ready: true,
      dependencies: {
        database: { ok: true, detail: "ok" },
        litellm: { ok: true, detail: "ok" },
      },
    } as never);
    vi.mocked(api.listAuditEvents).mockResolvedValue({
      events: [
        {
          id: 1,
          occurred_at: "2026-11-20T10:00:00Z",
          action: "key.regenerate",
          target: "personal key",
          actor_id: "demo-admin",
          actor_email: "alex@example.com",
          details: {},
          outcome: "success",
        },
      ],
    } as never);
  });

  function renderAt(entry: string) {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/status" element={<AdminStatus />} />
            <Route path="/audit" element={<AdminAudit />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("shows readiness on Status without the audit history", async () => {
    renderAt("/status");
    expect(
      await screen.findByText("LiteGate is ready to serve requests.", {
        exact: false,
      }),
    ).toBeVisible();
    expect(
      screen.queryByRole("region", { name: "Administrator audit history" }),
    ).not.toBeInTheDocument();
    expect(api.listAuditEvents).not.toHaveBeenCalled();
  });

  it("shows the audit history on its own page", async () => {
    renderAt("/audit");
    expect(
      await screen.findByRole("heading", { name: "Audit log", level: 1 }),
    ).toBeVisible();
    expect(await screen.findByText("key.regenerate")).toBeVisible();
    expect(api.getSystemStatus).not.toHaveBeenCalled();
  });

  it("sends old Status #audit links to the Audit log page", async () => {
    renderAt("/status#audit");
    expect(
      await screen.findByRole("heading", { name: "Audit log", level: 1 }),
    ).toBeVisible();
  });
});
