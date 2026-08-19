import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { api } from "../api/client";
import type { KeyInfo, KeySettingsUpdate } from "../types";

const inputClass = "rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none";

export default function BulkKeyEditor({ keys, isAdmin }: { keys: KeyInfo[]; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const keyToken = (key: KeyInfo) => key.token ?? key.api_key ?? key.key ?? "";
  const ownedTokens = useMemo(() => keys.map(keyToken).filter(Boolean), [keys]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [targets, setTargets] = useState("");
  const [alias, setAlias] = useState("");
  const [models, setModels] = useState("");
  const [budget, setBudget] = useState("");
  const [budgetDuration, setBudgetDuration] = useState("");
  const [tpm, setTpm] = useState("");
  const [rpm, setRpm] = useState("");
  const [duration, setDuration] = useState("");
  const [blocked, setBlocked] = useState("");
  const [localError, setLocalError] = useState("");

  const adminKeys = useQuery({
    queryKey: ["admin-keys", page],
    queryFn: () => api.listAllKeys(page, 25),
    enabled: isAdmin && editorOpen,
    placeholderData: previous => previous,
  });

  const update = useMutation({
    mutationFn: ({ targetKeys, settings }: { targetKeys: string[]; settings: KeySettingsUpdate }) => api.bulkUpdateKeys(targetKeys, settings),
    onSuccess: () => {
      setSelected([]);
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-keys"] });
    },
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setLocalError("");
    const targetKeys = isAdmin
      ? Array.from(new Set([
          ...selected,
          ...targets.split(/[\n,]/).map(value => value.trim()).filter(Boolean),
        ]))
      : ownedTokens;
    if (!targetKeys.length) { setLocalError("No editable key is available."); return; }
    const settings: KeySettingsUpdate = {};
    if (alias.trim()) settings.key_alias = alias.trim();
    if (models.trim()) settings.models = models.split(",").map(value => value.trim()).filter(Boolean);
    if (budget !== "") settings.max_budget = Number(budget);
    if (budgetDuration.trim()) settings.budget_duration = budgetDuration.trim();
    if (tpm !== "") settings.tpm_limit = Number(tpm);
    if (rpm !== "") settings.rpm_limit = Number(rpm);
    if (duration.trim()) settings.duration = duration.trim();
    if (blocked !== "") settings.blocked = blocked === "true";
    if (!Object.keys(settings).length) { setLocalError("Choose at least one setting to change."); return; }
    update.mutate({ targetKeys, settings });
  }

  const error = localError || (update.error as Error | null)?.message;
  const pageTokens = adminKeys.data?.keys.map(keyToken).filter(Boolean) ?? [];
  const allPageSelected = pageTokens.length > 0 && pageTokens.every(token => selected.includes(token));

  function toggleKey(token: string) {
    setSelected(current => current.includes(token)
      ? current.filter(value => value !== token)
      : [...current, token]);
  }

  function togglePage() {
    setSelected(current => allPageSelected
      ? current.filter(token => !pageTokens.includes(token))
      : Array.from(new Set([...current, ...pageTokens])));
  }

  return (
    <details onToggle={event => setEditorOpen(event.currentTarget.open)} className="w-full max-w-lg rounded-xl border border-[#2A2E42] bg-[#1A1D27]">
      <summary className="flex cursor-pointer list-none items-center gap-2 p-4 text-sm font-medium text-gray-200"><SlidersHorizontal size={16} /> Bulk edit key settings {selected.length > 0 && <span className="ml-auto rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] text-indigo-300">{selected.length} selected</span>}</summary>
      <form onSubmit={submit} className="grid gap-3 border-t border-[#2A2E42] p-4 sm:grid-cols-2">
        {isAdmin && <div className="space-y-2 sm:col-span-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-gray-300">1. Choose keys</p>
            {adminKeys.data && <span className="text-[10px] text-gray-500">{adminKeys.data.total} total</span>}
          </div>
          <div className="overflow-hidden rounded-lg border border-[#2A2E42] bg-[#0F1117]">
            {adminKeys.isLoading ? <div className="h-28 animate-pulse bg-[#22263A]" /> : adminKeys.error ? <p className="p-3 text-xs text-red-400">{(adminKeys.error as Error).message}</p> : adminKeys.data?.keys.length ? <>
              <label className="flex cursor-pointer items-center gap-3 border-b border-[#2A2E42] px-3 py-2 text-xs text-gray-400">
                <input type="checkbox" checked={allPageSelected} onChange={togglePage} /> Select this page
              </label>
              <div className="max-h-48 divide-y divide-[#22263A] overflow-y-auto">
                {adminKeys.data.keys.map((key, index) => {
                  const token = keyToken(key);
                  return <label key={token || index} className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-[#1A1D27]">
                    <input type="checkbox" checked={selected.includes(token)} onChange={() => toggleKey(token)} disabled={!token} />
                    <span className="min-w-0 flex-1"><span className="block truncate text-xs text-gray-200">{key.key_alias || `Key ${index + 1}`}</span><span className="block truncate font-mono text-[10px] text-gray-600">{token ? `${token.slice(0, 12)}...` : "No key ID"}</span></span>
                    <span className="max-w-28 truncate text-[10px] text-gray-500">{key.user_email || key.user_id}</span>
                  </label>;
                })}
              </div>
              <div className="flex items-center justify-between border-t border-[#2A2E42] px-3 py-2 text-xs">
                <button type="button" onClick={() => setPage(value => Math.max(1, value - 1))} disabled={page <= 1} className="text-gray-400 disabled:opacity-30">Previous</button>
                <span className="text-gray-600">Page {adminKeys.data.page} of {adminKeys.data.total_pages}</span>
                <button type="button" onClick={() => setPage(value => value + 1)} disabled={page >= adminKeys.data.total_pages} className="text-gray-400 disabled:opacity-30">Next</button>
              </div>
            </> : <p className="p-4 text-center text-xs text-gray-500">No keys found.</p>}
          </div>
          <details><summary className="cursor-pointer text-[11px] text-gray-500 hover:text-gray-300">Or paste key IDs manually</summary><textarea className={`${inputClass} mt-2 min-h-16 w-full`} value={targets} onChange={e => setTargets(e.target.value)} placeholder="One key per line" /></details>
        </div>}
        <p className="text-xs font-medium text-gray-300 sm:col-span-2">{isAdmin ? "2." : "1."} Choose settings to change</p>
        <input className={inputClass} value={alias} onChange={e => setAlias(e.target.value)} placeholder="Alias" />
        <input className={inputClass} value={models} onChange={e => setModels(e.target.value)} placeholder="Models, comma-separated" />
        <input className={inputClass} value={budget} onChange={e => setBudget(e.target.value)} type="number" min="0" step="any" placeholder="Max budget" />
        <input className={inputClass} value={budgetDuration} onChange={e => setBudgetDuration(e.target.value)} placeholder="Budget reset (e.g. 30d)" />
        <input className={inputClass} value={tpm} onChange={e => setTpm(e.target.value)} type="number" min="0" placeholder="TPM limit" />
        <input className={inputClass} value={rpm} onChange={e => setRpm(e.target.value)} type="number" min="0" placeholder="RPM limit" />
        <input className={inputClass} value={duration} onChange={e => setDuration(e.target.value)} placeholder="New duration (e.g. 90d)" />
        <select className={inputClass} value={blocked} onChange={e => setBlocked(e.target.value)}><option value="">Blocked: no change</option><option value="false">Unblock</option><option value="true">Block</option></select>
        {error && <p className="text-xs text-red-400 sm:col-span-2">{error}</p>}
        {update.data && <p className={`text-xs sm:col-span-2 ${update.data.failed ? "text-amber-300" : "text-green-400"}`}>{update.data.updated} updated, {update.data.failed} failed.</p>}
        <button disabled={update.isPending || (isAdmin && selected.length === 0 && !targets.trim())} className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 sm:col-span-2">{update.isPending ? "Updating..." : `Update ${isAdmin ? `${selected.length || targets.split(/[\n,]/).filter(Boolean).length} selected` : "my"} keys`}</button>
      </form>
    </details>
  );
}
