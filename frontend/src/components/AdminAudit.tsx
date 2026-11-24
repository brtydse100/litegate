import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api } from "../api/client";
import EmailAddress from "./EmailAddress";
import { PageHeader, Pill } from "./Page";
import { buttonSecondary, card, cardHeader, cardTitle, tableHead } from "./ui";

/** Administrator audit history, on its own page. */
export default function AdminAudit() {
  const audit = useQuery({
    queryKey: ["audit-events"],
    queryFn: () => api.listAuditEvents(100),
  });
  return (
    <section className="flex w-full flex-col gap-6">
      <PageHeader
        title="Audit log"
        description="Recent administrator activity."
        actions={
          <button
            type="button"
            onClick={() => void audit.refetch()}
            disabled={audit.isFetching}
            className={buttonSecondary}
          >
            <RefreshCw
              size={14}
              aria-hidden="true"
              className={audit.isFetching ? "animate-spin" : ""}
            />
            Refresh
          </button>
        }
      />

      <section
        aria-label="Administrator audit history"
        className={`overflow-hidden ${card}`}
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
          <div className="h-36 animate-pulse bg-well" />
        ) : audit.error ? (
          <p role="alert" className="p-5 text-sm text-danger">
            {(audit.error as Error).message}
          </p>
        ) : audit.data?.events.length ? (
          <div className="relative max-h-[36rem] overflow-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className={`sticky top-0 ${tableHead}`}>
                <tr>
                  <th className="px-5 py-2.5 font-semibold">Time</th>
                  <th className="px-3 py-2.5 font-semibold">Action</th>
                  <th className="px-3 py-2.5 font-semibold">Actor</th>
                  <th className="px-3 py-2.5 font-semibold">Details</th>
                  <th className="px-5 py-2.5 text-right font-semibold">
                    Outcome
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
