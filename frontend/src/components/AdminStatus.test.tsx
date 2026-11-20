import { MemoryRouter, useNavigate } from "react-router-dom";
import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

describe("audit log navigation", () => {
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    vi.mocked(api.getSystemStatus).mockResolvedValue({
      ready: true,
      dependencies: {
        database: { ok: true, detail: "ok" },
        litellm: { ok: true, detail: "ok" },
      },
    } as never);
    vi.mocked(api.listAuditEvents).mockResolvedValue({ events: [] });
    scrollIntoView.mockReset();
    // jsdom has no scrollIntoView; add it for these tests only.
    Element.prototype.scrollIntoView = scrollIntoView;
  });

  afterEach(() => {
    delete (Element.prototype as Partial<Element>).scrollIntoView;
  });

  function renderAt(entry: string) {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    let go: (to: string) => void = () => undefined;
    function Navigator() {
      const navigate = useNavigate();
      go = (to) => navigate(to);
      return null;
    }
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[entry]}>
          <Navigator />
          <AdminStatus />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return (to: string) => act(() => go(to));
  }

  it("scrolls to the audit once loaded and again on each repeat click", async () => {
    const navigate = renderAt("/status#audit");
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    navigate("/status#audit");
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(2));
  });

  it("still scrolls to the audit section when the audit request fails", async () => {
    vi.mocked(api.listAuditEvents).mockRejectedValue(new Error("Forbidden"));
    renderAt("/status#audit");
    expect(await screen.findByText("Forbidden")).toBeVisible();
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("returns to the top for plain Status", async () => {
    const navigate = renderAt("/status#audit");
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    navigate("/status");
    expect(window.scrollTo).toHaveBeenCalledTimes(1);
  });

  it("does not jump back to the top when audit data arrives later", async () => {
    let finish: (value: { events: never[] }) => void = () => undefined;
    vi.mocked(api.listAuditEvents).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    renderAt("/status");
    expect(window.scrollTo).toHaveBeenCalledTimes(1);
    await act(async () => finish({ events: [] }));
    expect(
      await screen.findByText(
        /No administrator actions have been recorded yet/,
      ),
    ).toBeVisible();
    expect(window.scrollTo).toHaveBeenCalledTimes(1);
  });
});
