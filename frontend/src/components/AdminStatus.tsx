import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, Database, RefreshCw, Server, XCircle } from "lucide-react";
import { api } from "../api/client";

function StatusCard({ name, detail, ok, icon }: { name: string; detail: string; ok: boolean; icon: React.ReactNode }) {
  return <div className="rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-4">
    <div className="flex items-start gap-3">
      <span className={`rounded-lg p-2 ${ok ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>{icon}</span>
      <div className="min-w-0 flex-1"><p className="text-sm font-medium text-white">{name}</p><p className="mt-1 text-xs leading-5 text-gray-500">{detail}</p></div>
      {ok ? <CheckCircle2 size={17} className="text-green-400" /> : <XCircle size={17} className="text-red-400" />}
    </div>
  </div>;
}

export default function AdminStatus() {
  const status = useQuery({ queryKey: ["system-status"], queryFn: api.getSystemStatus, refetchInterval: 30_000 });
  const audit = useQuery({ queryKey: ["audit-events"], queryFn: () => api.listAuditEvents(100) });

  return <section className="w-full max-w-5xl space-y-6">
    <div className="flex items-start justify-between gap-4">
      <div><p className="text-xs font-medium uppercase tracking-wider text-indigo-400">Operations</p><h1 className="mt-1 flex items-center gap-2 text-xl font-semibold text-white"><Activity size={20} /> System status</h1><p className="mt-1 text-sm text-gray-500">Dependency readiness and recent administrator activity.</p></div>
      <button onClick={() => { void status.refetch(); void audit.refetch(); }} disabled={status.isFetching || audit.isFetching} className="flex items-center gap-2 rounded-lg border border-[#2A2E42] px-3 py-2 text-xs text-gray-300 hover:bg-[#1A1D27] disabled:opacity-40"><RefreshCw size={13} className={status.isFetching || audit.isFetching ? "animate-spin" : ""} /> Refresh</button>
    </div>

    {status.error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{(status.error as Error).message}</p>}
    <div className="grid gap-3 md:grid-cols-2">
      <StatusCard name="LiteLLM" ok={status.data?.dependencies.litellm.ok ?? false} detail={status.isLoading ? "Checking connection..." : status.data?.dependencies.litellm.detail ?? "Status unavailable"} icon={<Server size={17} />} />
      <StatusCard name="Local account database" ok={status.data?.dependencies.database.ok ?? false} detail={status.isLoading ? "Checking storage..." : status.data?.dependencies.database.detail ?? "Status unavailable"} icon={<Database size={17} />} />
    </div>
    {status.data && <p className={`rounded-lg border px-4 py-3 text-sm ${status.data.ready ? "border-green-500/20 bg-green-500/5 text-green-300" : "border-red-500/20 bg-red-500/5 text-red-300"}`}>{status.data.ready ? "LiteGate is ready to serve requests." : "LiteGate is running, but one or more required dependencies are unavailable."} Storage mode: {status.data.storage_mode}.</p>}

    <div className="overflow-hidden rounded-xl border border-[#2A2E42] bg-[#1A1D27]">
      <div className="border-b border-[#2A2E42] px-4 py-3"><h2 className="text-sm font-medium text-gray-200">Administrator audit history</h2><p className="mt-1 text-xs text-gray-500">Secrets are redacted; bulk operations store counts instead of key identifiers.</p></div>
      {audit.isLoading ? <div className="h-36 animate-pulse bg-[#22263A]" /> : audit.error ? <p className="p-4 text-sm text-red-300">{(audit.error as Error).message}</p> : audit.data?.events.length ? <div className="max-h-[32rem] divide-y divide-[#2A2E42] overflow-y-auto">{audit.data.events.map(event => <div key={event.id} className="grid gap-1 px-4 py-3 text-xs sm:grid-cols-[10rem_1fr_auto] sm:items-center sm:gap-4"><time className="text-gray-600" dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time><div className="min-w-0"><p className="truncate text-gray-300"><span className="font-medium text-white">{event.action}</span> · {event.target}</p><p className="truncate text-gray-600">{event.actor_email || event.actor_id}{Object.keys(event.details).length ? ` · ${JSON.stringify(event.details)}` : ""}</p></div><span className={`w-fit rounded px-2 py-0.5 text-[10px] ${event.outcome === "success" ? "bg-green-500/10 text-green-300" : "bg-red-500/10 text-red-300"}`}>{event.outcome}</span></div>)}</div> : <p className="p-6 text-center text-sm text-gray-500">No administrator actions have been recorded yet.</p>}
    </div>
  </section>;
}
