import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, Search, SlidersHorizontal, UserRound, X } from "lucide-react";
import { api } from "../api/client";
import { useOperationLimit } from "../hooks/useOperationLimit";
import type { KeyInfo, KeySettingsUpdate } from "../types";

const inputClass = "rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none";

function keyToken(key: KeyInfo): string {
  return key.token ?? key.api_key ?? key.key ?? "";
}

function maskedToken(token: string): string {
  if (!token) return "Key identifier unavailable";
  if (token.length <= 16) return token;
  return `${token.slice(0, 9)}••••${token.slice(-4)}`;
}

export default function BulkKeyEditor() {
  const queryClient = useQueryClient();
  const { operationsBlocked, retryAfter, refreshOperationLimit } = useOperationLimit();
  const [editorOpen, setEditorOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("");
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
    enabled: editorOpen,
    placeholderData: previous => previous,
  });

  const selectAll = useMutation({
    mutationFn: api.listAllKeyIdentifiers,
    onSuccess: data => {
      setSelected(data.keys);
      setLocalError("");
    },
  });

  const update = useMutation({
    mutationFn: ({ targetKeys, settings }: { targetKeys: string[]; settings: KeySettingsUpdate }) => api.bulkUpdateKeys(targetKeys, settings),
    onSuccess: () => {
      setSelected([]);
      setTargets("");
      selectAll.reset();
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-keys"] });
    },
    onSettled: refreshOperationLimit,
  });

  const normalizedFilter = filter.trim().toLocaleLowerCase();
  const visibleKeys = (adminKeys.data?.keys ?? []).filter(key => {
    if (!normalizedFilter) return true;
    return [key.key_alias, key.user_email, key.user_id, key.team_id, keyToken(key)]
      .some(value => value?.toLocaleLowerCase().includes(normalizedFilter));
  });
  const visibleTokens = visibleKeys.map(keyToken).filter(Boolean);
  const allVisibleSelected = visibleTokens.length > 0 && visibleTokens.every(token => selected.includes(token));
  const allFetchedTokens = selectAll.data?.keys ?? [];
  const allKeysSelected = allFetchedTokens.length > 0
    && selectAll.data?.total === adminKeys.data?.total
    && allFetchedTokens.every(token => selected.includes(token));
  const pastedTokens = targets.split(/[\n,]/).map(value => value.trim()).filter(Boolean);
  const targetCount = new Set([...selected, ...pastedTokens]).size;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (operationsBlocked || update.isPending) return;
    setLocalError("");
    const targetKeys = Array.from(new Set([...selected, ...pastedTokens]));
    if (!targetKeys.length) { setLocalError("Select at least one key to update."); return; }
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

  function toggleKey(token: string) {
    setSelected(current => current.includes(token)
      ? current.filter(value => value !== token)
      : [...current, token]);
  }

  function toggleVisible() {
    setSelected(current => allVisibleSelected
      ? current.filter(token => !visibleTokens.includes(token))
      : Array.from(new Set([...current, ...visibleTokens])));
  }

  function toggleAllKeys() {
    if (allKeysSelected) {
      const allTokenSet = new Set(allFetchedTokens);
      setSelected(current => current.filter(token => !allTokenSet.has(token)));
      return;
    }
    setLocalError("");
    selectAll.mutate();
  }

  const error = localError
    || (selectAll.error as Error | null)?.message
    || (update.error as Error | null)?.message;

  return (
    <details onToggle={event => setEditorOpen(event.currentTarget.open)} className="w-full max-w-2xl rounded-xl border border-[#2A2E42] bg-[#1A1D27]">
      <summary className="flex cursor-pointer list-none items-center gap-2 p-4 text-sm font-medium text-gray-200">
        <SlidersHorizontal size={16} /> Bulk edit key settings
        {targetCount > 0 && <span className="ml-auto rounded-full bg-indigo-500/15 px-2.5 py-1 text-[10px] font-semibold text-indigo-300">{targetCount} selected</span>}
      </summary>
      <form onSubmit={submit} className="grid gap-4 border-t border-[#2A2E42] p-4 sm:grid-cols-2">
        <div className="space-y-3 sm:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div><p className="text-xs font-semibold text-gray-200">1. Choose keys</p><p className="mt-0.5 text-[11px] text-gray-600">Selections stay checked while you move between pages.</p></div>
            {adminKeys.data && <span className="shrink-0 text-[10px] text-gray-500">{adminKeys.data.total} total</span>}
          </div>

          <div className="overflow-hidden rounded-xl border border-[#2A2E42] bg-[#0F1117]">
            <div className="space-y-2 border-b border-[#2A2E42] bg-[#151822] p-3">
              <div className="relative">
                <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
                <input aria-label="Filter keys on this page" value={filter} onChange={event => setFilter(event.target.value)} className={`${inputClass} w-full pl-9 pr-9`} placeholder="Filter this page by key, user, or team" />
                {filter && <button type="button" onClick={() => setFilter("")} aria-label="Clear key filter" className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-gray-600 hover:bg-[#22263A] hover:text-white"><X size={13} /></button>}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${selected.length ? "bg-indigo-500/15 text-indigo-300" : "bg-[#22263A] text-gray-500"}`}>{selected.length} selected</span>
                <div className="flex items-center gap-2">
                  {selected.length > 0 && <button type="button" onClick={() => setSelected([])} className="rounded-lg px-2.5 py-1.5 text-[11px] text-gray-400 hover:bg-[#22263A] hover:text-white">Clear all</button>}
                  <button type="button" onClick={toggleAllKeys} disabled={!adminKeys.data?.total || selectAll.isPending} className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-2.5 py-1.5 text-[11px] font-medium text-cyan-300 hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-35">{selectAll.isPending ? "Selecting all..." : allKeysSelected ? `Deselect all (${allFetchedTokens.length})` : `Select all keys (${adminKeys.data?.total ?? 0})`}</button>
                  <button type="button" onClick={toggleVisible} disabled={!visibleTokens.length} className="rounded-lg border border-indigo-500/25 bg-indigo-500/10 px-2.5 py-1.5 text-[11px] font-medium text-indigo-300 hover:bg-indigo-500/20 disabled:cursor-not-allowed disabled:opacity-35">{allVisibleSelected ? "Deselect visible" : `Select visible (${visibleTokens.length})`}</button>
                </div>
              </div>
            </div>

            {adminKeys.isLoading ? <div className="h-44 animate-pulse bg-[#22263A]" /> : adminKeys.error ? <p className="p-4 text-xs text-red-400">{(adminKeys.error as Error).message}</p> : adminKeys.data?.keys.length ? <>
              <div className="max-h-80 space-y-2 overflow-y-auto p-2">
                {visibleKeys.length ? visibleKeys.map((key, index) => {
                  const token = keyToken(key);
                  const isSelected = Boolean(token && selected.includes(token));
                  const label = key.key_alias || `Key ${(adminKeys.data?.page ?? page) * 25 - 24 + index}`;
                  return <label key={token || index} className={`group flex items-center gap-3 rounded-lg border p-3 transition focus-within:ring-2 focus-within:ring-indigo-500/50 ${!token ? "cursor-not-allowed border-transparent opacity-40" : isSelected ? "cursor-pointer border-indigo-500/55 bg-indigo-500/10 shadow-sm shadow-indigo-950/40" : "cursor-pointer border-transparent bg-[#151822] hover:border-[#353A52] hover:bg-[#1A1D27]"}`}>
                    <input className="sr-only" type="checkbox" checked={isSelected} onChange={() => toggleKey(token)} disabled={!token} aria-label={`${isSelected ? "Deselect" : "Select"} ${label}`} />
                    <span aria-hidden="true" className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition ${isSelected ? "border-indigo-400 bg-indigo-500 text-white" : "border-gray-600 bg-[#0F1117] group-hover:border-indigo-400"}`}>{isSelected && <Check size={13} strokeWidth={3} />}</span>
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${isSelected ? "bg-indigo-500/20 text-indigo-300" : "bg-[#22263A] text-gray-500"}`}><KeyRound size={16} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium text-gray-200">{label}</span>
                      <span className="mt-0.5 block truncate font-mono text-[10px] text-gray-600">{maskedToken(token)}</span>
                      <span className="mt-1 flex min-w-0 items-center gap-1 text-[10px] text-gray-500"><UserRound size={10} className="shrink-0" /><span className="truncate">{key.user_email || key.user_id || "Unassigned user"}</span></span>
                    </span>
                    <span className="hidden shrink-0 flex-col items-end gap-1 sm:flex">
                      <span className="rounded bg-[#22263A] px-2 py-0.5 text-[10px] text-gray-400">${(key.spend ?? 0).toFixed(2)} spent</span>
                      {key.team_id && <span className="max-w-32 truncate rounded bg-cyan-500/10 px-2 py-0.5 text-[10px] text-cyan-300" title={key.team_id}>{key.team_id}</span>}
                    </span>
                  </label>;
                }) : <p className="p-8 text-center text-xs text-gray-500">No keys on this page match “{filter}”.</p>}
              </div>
              <div className="flex items-center justify-between border-t border-[#2A2E42] bg-[#151822] px-3 py-2.5 text-xs">
                <button type="button" onClick={() => setPage(value => Math.max(1, value - 1))} disabled={page <= 1 || adminKeys.isFetching} className="rounded px-2 py-1 text-gray-400 hover:bg-[#22263A] hover:text-white disabled:opacity-30">Previous</button>
                <span className="text-gray-600">Page {adminKeys.data.page} of {adminKeys.data.total_pages}</span>
                <button type="button" onClick={() => setPage(value => value + 1)} disabled={page >= adminKeys.data.total_pages || adminKeys.isFetching} className="rounded px-2 py-1 text-gray-400 hover:bg-[#22263A] hover:text-white disabled:opacity-30">Next</button>
              </div>
            </> : <p className="p-8 text-center text-xs text-gray-500">No keys found.</p>}
          </div>

          <details className="rounded-lg border border-dashed border-[#2A2E42] px-3 py-2.5"><summary className="cursor-pointer text-[11px] text-gray-500 hover:text-gray-300">Advanced: paste key IDs manually</summary><textarea className={`${inputClass} mt-3 min-h-20 w-full`} value={targets} onChange={event => setTargets(event.target.value)} placeholder="One key ID per line" /></details>
        </div>

        <div className="sm:col-span-2"><p className="text-xs font-semibold text-gray-200">2. Choose settings to change</p><p className="mt-0.5 text-[11px] text-gray-600">Only filled fields are changed for the selected keys.</p></div>
        <input className={inputClass} value={alias} onChange={event => setAlias(event.target.value)} placeholder="Alias" />
        <input className={inputClass} value={models} onChange={event => setModels(event.target.value)} placeholder="Models, comma-separated" />
        <input className={inputClass} value={budget} onChange={event => setBudget(event.target.value)} type="number" min="0" step="any" placeholder="Max budget" />
        <input className={inputClass} value={budgetDuration} onChange={event => setBudgetDuration(event.target.value)} placeholder="Budget reset (e.g. 30d)" />
        <input className={inputClass} value={tpm} onChange={event => setTpm(event.target.value)} type="number" min="0" placeholder="TPM limit" />
        <input className={inputClass} value={rpm} onChange={event => setRpm(event.target.value)} type="number" min="0" placeholder="RPM limit" />
        <input className={inputClass} value={duration} onChange={event => setDuration(event.target.value)} placeholder="New duration (e.g. 90d)" />
        <select aria-label="Blocked setting" className={inputClass} value={blocked} onChange={event => setBlocked(event.target.value)}><option value="">Blocked: no change</option><option value="false">Unblock</option><option value="true">Block</option></select>
        {error && <p className="text-xs text-red-400 sm:col-span-2">{error}</p>}
        {operationsBlocked && <p className="text-xs text-amber-300 sm:col-span-2">Bulk updates are paused. Try again in {retryAfter || 1} seconds.</p>}
        {update.data && <p className={`text-xs sm:col-span-2 ${update.data.failed ? "text-amber-300" : "text-green-400"}`}>{update.data.updated} updated, {update.data.failed} failed.</p>}
        <button disabled={update.isPending || operationsBlocked || targetCount === 0} className="rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-950/30 hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2">{update.isPending ? "Updating..." : operationsBlocked ? "Bulk updates paused" : targetCount ? `Apply settings to ${targetCount} ${targetCount === 1 ? "key" : "keys"}` : "Select keys to continue"}</button>
      </form>
    </details>
  );
}
