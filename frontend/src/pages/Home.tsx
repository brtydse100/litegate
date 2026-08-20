import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, Copy, ExternalLink, Gauge, KeyRound, LogOut, RefreshCw, Shield, Ticket, Users, Zap } from "lucide-react";
import AdminUsers from "../components/AdminUsers";
import AdminTeams from "../components/AdminTeams";
import BulkKeyEditor from "../components/BulkKeyEditor";
import { api } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import type { KeyInfo } from "../types";

interface PortalConfig {
  support_ticket_url: string;
  logo_url: string;
  litellm_ui_url: string;
  api_docs_url: string;
}

async function fetchPortalConfig(): Promise<PortalConfig> {
  const response = await fetch("/api/portal-config");
  if (!response.ok) throw new Error("Could not load portal configuration");
  return response.json();
}

function KeyCard({ keyInfo }: { keyInfo: KeyInfo }) {
  const [copied, setCopied] = useState(false);
  const token = keyInfo.token ?? "";
  const display = token ? `${token.slice(0, 9)}${"•".repeat(8)}${token.slice(-4)}` : "Hidden — regenerate to reveal";

  async function copy() {
    if (!token) return;
    await navigator.clipboard.writeText(token);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <article className="w-full max-w-lg space-y-4 rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-5">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-indigo-500/10 p-2 text-indigo-300"><KeyRound size={17} /></div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-gray-500">{keyInfo.key_alias || "API key"}</p>
          <code className="block truncate font-mono text-sm text-gray-200">{display}</code>
        </div>
        {token && <button onClick={copy} title="Copy key identifier" className="text-gray-500 hover:text-white">{copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} />}</button>}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-gray-500">
        <span>Spend <b className="font-medium text-gray-300">${keyInfo.spend.toFixed(4)}</b></span>
        {keyInfo.max_budget != null && <span>Budget <b className="font-medium text-gray-300">${keyInfo.max_budget}</b></span>}
        {keyInfo.expires && <span>Expires <b className="font-medium text-gray-300">{new Date(keyInfo.expires).toLocaleDateString()}</b></span>}
        <span>Models <b className="font-medium text-gray-300">{keyInfo.models?.length ? keyInfo.models.length : "All"}</b></span>
        {keyInfo.team_id && <span className="flex min-w-0 items-center gap-1"><Building2 size={12} /><span>Team</span> <b className="max-w-48 truncate font-medium text-gray-300" title={keyInfo.team_id}>{keyInfo.team_id}</b></span>}
      </div>
    </article>
  );
}

function AccessSnapshot({ keys }: { keys: KeyInfo[] }) {
  const first = keys[0];
  const limit = first?.rpm_limit != null ? `${first.rpm_limit.toLocaleString()} RPM` : "Default limits";
  const models = first?.models?.length ? `${first.models.length} models` : "All allowed models";
  return (
    <section className="grid w-full max-w-lg grid-cols-3 gap-3" aria-label="Access snapshot">
      <div className="rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-3 text-center"><Check size={16} className="mx-auto text-green-400" /><p className="mt-1 text-sm font-medium text-white">Ready</p><p className="text-[11px] text-gray-500">Status</p></div>
      <div className="rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-3 text-center"><Zap size={16} className="mx-auto text-indigo-400" /><p className="mt-1 truncate text-sm font-medium text-white">{models}</p><p className="text-[11px] text-gray-500">Access</p></div>
      <div className="rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-3 text-center"><Gauge size={16} className="mx-auto text-amber-400" /><p className="mt-1 truncate text-sm font-medium text-white">{limit}</p><p className="text-[11px] text-gray-500">Rate</p></div>
    </section>
  );
}

export default function Home() {
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"keys" | "users" | "teams">("keys");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);

  const portal = useQuery({ queryKey: ["portal-config"], queryFn: fetchPortalConfig, staleTime: Infinity });
  const keys = useQuery({ queryKey: ["keys"], queryFn: api.listKeys });
  const keyList = keys.data?.keys ?? [];
  const hasKey = keyList.length > 0;

  const create = useMutation({ mutationFn: api.createKey, onSuccess: result => { setNewKey(result.key); void queryClient.invalidateQueries({ queryKey: ["keys"] }); } });
  const regenerate = useMutation({ mutationFn: api.regenerateKey, onSuccess: result => { setNewKey(result.key); setConfirmRegenerate(false); void queryClient.invalidateQueries({ queryKey: ["keys"] }); } });
  const mutationError = create.error ?? regenerate.error ?? keys.error;

  async function copyNewKey() {
    if (!newKey) return;
    await navigator.clipboard.writeText(newKey);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  const config = portal.data;
  const isAdmin = user?.role === "admin";

  return (
    <div className="min-h-screen bg-[#0F1117]">
      <header className="sticky top-0 z-10 border-b border-[#2A2E42] bg-[#1A1D27]/95 px-4 py-3 backdrop-blur sm:px-6">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {config?.logo_url ? <img src={config.logo_url} alt="Logo" className="h-8 w-auto object-contain" /> : <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600"><Zap size={15} /></div>}
            <span className="text-sm font-bold tracking-wide text-white">LiteGate</span>
          </div>
          <div className="flex items-center gap-3">
            {config?.api_docs_url && <a href={config.api_docs_url} target="_blank" rel="noreferrer" className="hidden text-xs text-gray-400 hover:text-white sm:block">API docs</a>}
            {user?.team_ids?.length ? <span className="hidden max-w-56 items-center gap-1 rounded-full bg-cyan-500/10 px-2 py-1 text-[10px] text-cyan-300 lg:flex" title={user.team_ids.join(", ")}><Building2 size={10} /><span className="truncate">{user.team_ids[0]}{user.team_ids.length > 1 ? ` +${user.team_ids.length - 1}` : ""}</span></span> : null}
            {isAdmin && <span className="hidden items-center gap-1 rounded-full bg-indigo-500/10 px-2 py-1 text-[10px] text-indigo-300 sm:flex"><Shield size={10} /> Admin</span>}
            <span className="hidden max-w-52 truncate text-xs text-gray-500 md:block">{user?.email}</span>
            <button onClick={logout} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white"><LogOut size={14} /> Sign out</button>
          </div>
        </div>
      </header>

      {isAdmin && <nav className="mx-auto flex max-w-6xl gap-1 px-4 pt-5 sm:px-6">
        <button onClick={() => setTab("keys")} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${tab === "keys" ? "bg-indigo-600 text-white" : "text-gray-400 hover:bg-[#1A1D27]"}`}><KeyRound size={15} /> Keys</button>
        <button onClick={() => setTab("users")} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${tab === "users" ? "bg-indigo-600 text-white" : "text-gray-400 hover:bg-[#1A1D27]"}`}><Users size={15} /> Users</button>
        <button onClick={() => setTab("teams")} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${tab === "teams" ? "bg-indigo-600 text-white" : "text-gray-400 hover:bg-[#1A1D27]"}`}><Building2 size={15} /> Teams</button>
      </nav>}

      <main className={`mx-auto flex max-w-6xl flex-col items-center gap-6 px-4 pb-16 ${isAdmin ? "pt-8" : "pt-12"} sm:px-6`}>
        {tab === "users" && isAdmin ? <AdminUsers /> : tab === "teams" && isAdmin ? <AdminTeams /> : <>
          <div className="max-w-xl text-center">
            <h1 className="text-3xl font-bold text-white">Your API access</h1>
            <p className="mt-2 text-sm text-gray-500">Create and manage a LiteLLM key without loading expensive usage logs.</p>
          </div>

          {mutationError && <p className="w-full max-w-lg rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-center text-sm text-red-300">{(mutationError as Error).message}</p>}

          {newKey && <div className="w-full max-w-lg space-y-3 rounded-xl border border-green-500/30 bg-green-500/10 p-5">
            <p className="text-center text-sm font-medium text-green-300">Copy this key now — it will not be shown in full again.</p>
            <div className="flex gap-2"><code className="min-w-0 flex-1 truncate rounded bg-[#0F1117] px-3 py-2 text-sm text-green-200">{newKey}</code><button onClick={copyNewKey} className="rounded bg-green-500/15 px-3 text-green-300">{copied ? <Check size={15} /> : <Copy size={15} />}</button></div>
            <button onClick={() => setNewKey(null)} className="w-full text-xs text-gray-500 hover:text-white">Dismiss</button>
          </div>}

          {confirmRegenerate && <div className="w-full max-w-lg space-y-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-5">
            <p className="text-sm font-medium text-amber-200">Replace the current key?</p><p className="text-xs text-gray-400">The old key stops working immediately.</p>
            <div className="flex gap-2"><button onClick={() => regenerate.mutate()} disabled={regenerate.isPending} className="rounded-lg bg-amber-600 px-4 py-2 text-xs font-medium text-white disabled:opacity-50">{regenerate.isPending ? "Replacing..." : "Replace key"}</button><button onClick={() => setConfirmRegenerate(false)} className="rounded-lg border border-[#2A2E42] px-4 py-2 text-xs text-gray-300">Cancel</button></div>
          </div>}

          {keys.isLoading ? <div className="h-28 w-full max-w-lg animate-pulse rounded-xl bg-[#1A1D27]" /> : keyList.map((keyInfo, index) => <KeyCard key={keyInfo.token ?? index} keyInfo={keyInfo} />)}

          {!keys.isLoading && !confirmRegenerate && (!hasKey ? <button onClick={() => create.mutate()} disabled={create.isPending} className="w-full max-w-lg rounded-2xl bg-indigo-600 px-8 py-5 text-lg font-bold text-white shadow-xl shadow-indigo-600/25 hover:bg-indigo-500 disabled:opacity-50"><span className="flex items-center justify-center gap-2"><Zap size={23} />{create.isPending ? "Creating..." : "Create API key"}</span></button> : <button onClick={() => setConfirmRegenerate(true)} className="flex w-full max-w-lg items-center justify-center gap-2 rounded-xl border border-[#2A2E42] px-5 py-3 text-sm text-gray-300 hover:bg-[#1A1D27]"><RefreshCw size={15} /> Regenerate key</button>)}

          {hasKey && <AccessSnapshot keys={keyList} />}
          {isAdmin && <BulkKeyEditor />}

          {(config?.litellm_ui_url || config?.support_ticket_url) && <div className="flex w-full max-w-lg flex-col gap-3 sm:flex-row">
            {config.litellm_ui_url && <a href={config.litellm_ui_url} target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-600/10 px-5 py-3 text-sm text-indigo-300 hover:bg-indigo-600/20"><ExternalLink size={15} /> Model hub</a>}
            {config.support_ticket_url && <a href={config.support_ticket_url} target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-[#2A2E42] bg-[#1A1D27] px-5 py-3 text-sm text-gray-300 hover:bg-[#22263A]"><Ticket size={15} /> Support</a>}
          </div>}
        </>}
      </main>
    </div>
  );
}
