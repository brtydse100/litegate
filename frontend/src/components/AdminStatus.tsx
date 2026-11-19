import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { api } from "../api/client";
import EmailAddress from "./EmailAddress";
import DismissibleMessage from "./DismissibleMessage";
import { MetricCard, PageHeader, Pill } from "./Page";
import { buttonSecondary, card, cardHeader, cardTitle, tableHead } from "./ui";

function Dependency({
  name,
  ok,
  detail,
  loading,
}: {
  name: string;
  ok: boolean;
  detail: string;
  loading: boolean;
}) {
  return (
    <MetricCard
      accent={
        loading
          ? "border-t-line-input"
          : ok
            ? "border-t-mint"
            : "border-t-danger"
      }
      caption={name}
      value={
        <>
          <span
            aria-hidden="true"
            className={`h-2 w-2 rounded-full ${loading ? "bg-ink-5" : ok ? "bg-mint" : "bg-danger"}`}
          />
          {loading ? "Checking…" : ok ? "Operational" : "Unavailable"}
        </>
      }
      sub={detail}
    />
  );
}

export default function AdminStatus() {
  const status = useQuery({
    queryKey: ["system-status"],
    queryFn: api.getSystemStatus,
    refetchInterval: 30_000,
  });
  const audit = useQuery({
    queryKey: ["audit-events"],
    queryFn: () => api.listAuditEvents(100),
  });
  const refreshing = status.isFetching || audit.isFetching;
  // The sidebar's Audit log link opens this page at #audit.
  const hash = window.location.hash;
  const auditLoaded = !!audit.data;
  useEffect(() => {
    if (hash === "#audit" && auditLoaded)
      document.getElementById("audit")?.scrollIntoView?.({ block: "start" });
  }, [hash, auditLoaded]);
  const warnings = status.data?.security_warnings ?? [];

  return (
    <section className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="System"
        title="System status"
        description="Dependency readiness and recent administrator activity."
        actions={
          <button
            type="button"
            onClick={() => {
              void status.refetch();
              void audit.refetch();
            }}
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
          className="rounded-xl border border-danger-line bg-danger-tint px-4 py-3 text-sm text-danger"
        >
          {(status.error as Error).message}
        </DismissibleMessage>
      )}

      {status.data && (
        <div
          className={`flex items-center gap-3 rounded-xl border px-4 py-3.5 text-sm ${
            status.data.ready
              ? "border-mint/40 bg-mint-tint text-mint-ink"
              : "border-danger-line bg-danger-tint text-danger"
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

      <div className="grid gap-3.5 md:grid-cols-2">
        <Dependency
          name="LiteLLM gateway"
          loading={status.isLoading}
          ok={status.data?.dependencies.litellm.ok ?? false}
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
          ok={status.data?.dependencies.database.ok ?? false}
          detail={
            status.isLoading
              ? "Checking storage..."
              : (status.data?.dependencies.database.detail ??
                "Status unavailable")
          }
        />
      </div>

      {warnings.length > 0 && (
        <div className="rounded-xl border border-sand/40 bg-sand-tint px-4 py-3.5 text-sand-ink">
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

      <section
        id="audit"
        aria-label="Administrator audit history"
        className={`scroll-mt-6 overflow-hidden ${card}`}
      >
        <div className={cardHeader}>
          <div>
            <h2 className={cardTitle}>Administrator audit history</h2>
            <p className="mt-0.5 text-[13px] text-ink-4">
              Secrets are redacted; bulk operations store counts instead of key
              identifiers.
            </p>
          </div>
        </div>
        {audit.isLoading ? (
          <div className="h-36 animate-pulse bg-canvas" />
        ) : audit.error ? (
          <p role="alert" className="p-5 text-sm text-danger">
            {(audit.error as Error).message}
          </p>
        ) : audit.data?.events.length ? (
          <div className="max-h-[36rem] overflow-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className={`sticky top-0 ${tableHead}`}>
                <tr>
                  <th className="px-5 py-2.5 font-semibold">TIME</th>
                  <th className="px-3 py-2.5 font-semibold">ACTION</th>
                  <th className="px-3 py-2.5 font-semibold">ACTOR</th>
                  <th className="px-3 py-2.5 font-semibold">DETAILS</th>
                  <th className="px-5 py-2.5 text-right font-semibold">
                    OUTCOME
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {audit.data.events.map((event) => (
                  <tr key={event.id} className="align-top">
                    <td className="whitespace-nowrap px-5 py-3 text-[13px] text-ink-4">
                      <time dateTime={event.occurred_at}>
                        {new Date(event.occurred_at).toLocaleString()}
                      </time>
                    </td>
                    <td className="px-3 py-3">
                      <p className="font-mono text-[13px] font-medium text-ink">
                        {event.action}
                      </p>
                      <p className="text-[13px] text-ink-3">{event.target}</p>
                    </td>
                    <td className="max-w-[16rem] break-all px-3 py-3 text-[13px] text-ink-2">
                      {event.actor_email ? (
                        <EmailAddress email={event.actor_email} />
                      ) : (
                        event.actor_id
                      )}
                    </td>
                    <td className="max-w-[18rem] break-all px-3 py-3 font-mono text-xs text-ink-4">
                      {Object.keys(event.details).length
                        ? JSON.stringify(event.details)
                        : "—"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Pill tone={event.outcome === "success" ? "ok" : "bad"}>
                        {event.outcome}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="p-6 text-center text-sm text-ink-4">
            No administrator actions have been recorded yet.
          </p>
        )}
      </section>
    </section>
  );
}
