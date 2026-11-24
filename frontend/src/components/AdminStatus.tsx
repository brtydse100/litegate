import { Navigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { api } from "../api/client";
import DismissibleMessage from "./DismissibleMessage";
import { PageHeader } from "./Page";
import { buttonSecondary, card } from "./ui";

function Dependency({
  name,
  ok,
  detail,
  loading,
}: {
  name: string;
  /** `null` when no status response arrived, so the state is unknown. */
  ok: boolean | null;
  detail: string;
  loading: boolean;
}) {
  const state = loading
    ? "Checking…"
    : ok === null
      ? "Unknown"
      : ok
        ? "Operational"
        : "Unavailable";
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-3.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{name}</p>
        <p className="mt-0.5 text-[13px] text-ink-4">{detail}</p>
      </div>
      <span className="inline-flex shrink-0 items-center gap-2 text-sm font-medium text-ink">
        <span
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${loading || ok === null ? "bg-ink-5" : ok ? "bg-green" : "bg-danger"}`}
        />
        {state}
      </span>
    </div>
  );
}

export default function AdminStatus() {
  const status = useQuery({
    queryKey: ["system-status"],
    queryFn: api.getSystemStatus,
    refetchInterval: 30_000,
  });
  const refreshing = status.isFetching;
  // Old "Audit log" links pointed at this page's #audit section.
  const location = useLocation();
  if (location.hash === "#audit") return <Navigate to="/audit" replace />;
  const warnings = status.data?.security_warnings ?? [];

  return (
    <section className="flex w-full flex-col gap-6">
      <PageHeader
        title="System status"
        description="Dependency readiness for LiteGate and LiteLLM."
        actions={
          <button
            type="button"
            onClick={() => void status.refetch()}
            disabled={refreshing}
            className={buttonSecondary}
          >
            <RefreshCw
              size={14}
              aria-hidden="true"
              className={refreshing ? "animate-spin" : ""}
            />
            Refresh
          </button>
        }
      />

      {status.error && (
        <DismissibleMessage
          role="alert"
          messageKey={(status.error as Error).message}
          className="rounded-xl border border-transparent bg-danger-tint px-4 py-3 text-sm text-danger"
        >
          {(status.error as Error).message}
        </DismissibleMessage>
      )}

      {status.data && (
        <div
          className={`flex items-center gap-3 rounded-xl border px-4 py-3.5 text-sm ${
            status.data.ready
              ? "border-transparent bg-green-tint text-green-ink"
              : "border-transparent bg-danger-tint text-danger"
          }`}
        >
          {status.data.ready ? (
            <CheckCircle2 size={18} aria-hidden="true" />
          ) : (
            <XCircle size={18} aria-hidden="true" />
          )}
          <p>
            <span className="font-semibold">
              {status.data.ready
                ? "LiteGate is ready to serve requests."
                : "LiteGate is running, but one or more required dependencies are unavailable."}
            </span>{" "}
            Storage mode: {status.data.storage_mode}.
          </p>
        </div>
      )}

      <div className={`${card} divide-y divide-line-soft`}>
        <Dependency
          name="LiteLLM gateway"
          loading={status.isLoading}
          ok={status.data ? status.data.dependencies.litellm.ok : null}
          detail={
            status.isLoading
              ? "Checking connection..."
              : (status.data?.dependencies.litellm.detail ??
                "Status unavailable")
          }
        />
        <Dependency
          name="Local account database"
          loading={status.isLoading}
          ok={status.data ? status.data.dependencies.database.ok : null}
          detail={
            status.isLoading
              ? "Checking storage..."
              : (status.data?.dependencies.database.detail ??
                "Status unavailable")
          }
        />
      </div>

      {warnings.length > 0 && (
        <div className="rounded-xl border border-transparent bg-orange-tint px-4 py-3.5 text-orange-ink">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle size={16} aria-hidden="true" /> Deployment security
            warnings
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
