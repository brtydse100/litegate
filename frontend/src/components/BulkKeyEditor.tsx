import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, KeyRound, Search, SlidersHorizontal, UserRound, X } from "lucide-react";
import { api } from "../api/client";
import { useOperationLimit } from "../hooks/useOperationLimit";
import type { AdminKeyFilters, BulkKeyUpdateResponse, KeyInfo, KeySettingsUpdate } from "../types";

const inputClass = "rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none";
const fieldClass = "space-y-1 text-xs text-gray-400";

export function keyToken(key: KeyInfo): string {
  return key.token ?? key.api_key ?? key.key ?? "";
}

export function maskedToken(token: string): string {
  if (!token) return "Key identifier unavailable";
  if (token.length <= 16) return token;
  return `${token.slice(0, 9)}....${token.slice(-4)}`;
}

export default function BulkKeyEditor({ expanded = false }: { expanded?: boolean }) {
  const queryClient = useQueryClient();
  const { operationsBlocked, retryAfter, refreshOperationLimit } = useOperationLimit();
  const [editorOpen, setEditorOpen] = useState(expanded);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [blockedFilter, setBlockedFilter] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [targets, setTargets] = useState("");
  const [alias, setAlias] = useState("");
  const [models, setModels] = useState("");
  const [budget, setBudget] = useState("");
  const [budgetDuration, setBudgetDuration] = useState("");
  const [tpm, setTpm] = useState("");
  const [rpm, setRpm] = useState("");
  const [duration, setDuration] = useState("");
  const [blockedSetting, setBlockedSetting] = useState("");
  const [localError, setLocalError] = useState("");
  const [lastSettings, setLastSettings] = useState<KeySettingsUpdate | null>(null);

  const filters: AdminKeyFilters = {
    ...(search ? { search } : {}),
    ...(teamFilter.trim() ? { team_id: teamFilter.trim() } : {}),
    ...(blockedFilter ? { blocked: blockedFilter === "true" } : {}),
  };
  const hasFilters = Boolean(search || teamFilter.trim() || blockedFilter);

  const adminKeys = useQuery({
    queryKey: ["admin-keys", page, search, teamFilter, blockedFilter],
    queryFn: () => api.listAllKeys(page, 25, filters),
    enabled: editorOpen || expanded,
    placeholderData: previous => previous,
  });

  const selectAll = useMutation({
    mutationFn: () => api.listAllKeyIdentifiers(filters),
    onSuccess: data => {
      setSelected(data.keys);
      setLocalError("");
    },
  });

  const update = useMutation({
    mutationFn: ({ targetKeys, settings }: { targetKeys: string[]; settings: KeySettingsUpdate }) => api.bulkUpdateKeys(targetKeys, settings),
    onSuccess: data => {
      const failedKeys = data.results.filter(result => !result.updated).map(result => result.key);
      setSelected(failedKeys);
      setTargets("");
      if (!failedKeys.length) selectAll.reset();
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-keys"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-events"] });
    },
    onSettled: refreshOperationLimit,
  });

  const visibleKeys = adminKeys.data?.keys ?? [];
  const visibleTokens = visibleKeys.map(keyToken).filter(Boolean);
  const allVisibleSelected = visibleTokens.length > 0 && visibleTokens.every(token => selected.includes(token));
  const allFetchedTokens = selectAll.data?.keys ?? [];
  const allKeysSelected = allFetchedTokens.length > 0
    && selectAll.data?.total === adminKeys.data?.total
    && allFetchedTokens.every(token => selected.includes(token));
  const pastedTokens = targets.split(/[\n,]/).map(value => value.trim()).filter(Boolean);
  const targetCount = new Set([...selected, ...pastedTokens]).size;
  const failedResults = update.data?.results.filter(result => !result.updated) ?? [];

  function settingsFromForm(): KeySettingsUpdate {
    const settings: KeySettingsUpdate = {};
    if (alias.trim()) settings.key_alias = alias.trim();
    if (models.trim()) settings.models = models.split(/[\n,]/).map(value => value.trim()).filter(Boolean);
    if (budget !== "") settings.max_budget = Number(budget);
    if (budgetDuration.trim()) settings.budget_duration = budgetDuration.trim();
    if (tpm !== "") settings.tpm_limit = Number(tpm);
    if (rpm !== "") settings.rpm_limit = Number(rpm);
    if (duration.trim()) settings.duration = duration.trim();
    if (blockedSetting !== "") settings.blocked = blockedSetting === "true";
    return settings;
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (operationsBlocked || update.isPending) return;
    setLocalError("");
    const targetKeys = Array.from(new Set([...selected, ...pastedTokens]));
    if (!targetKeys.length) { setLocalError("Select at least one key to update."); return; }
    const settings = settingsFromForm();
    if (!Object.keys(settings).length) { setLocalError("Choose at least one setting to change."); return; }
    setLastSettings(settings);
    update.mutate({ targetKeys, settings });
  }

  function applySearch() {
    setPage(1);
    setSearch(searchInput.trim());
    selectAll.reset();
  }

  function clearFilters() {
    setSearchInput("");
    setSearch("");
    setTeamFilter("");
    setBlockedFilter("");
    setPage(1);
    selectAll.reset();
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

  function retryFailures() {
    if (!lastSettings || !failedResults.length || operationsBlocked || update.isPending) return;
    update.mutate({ targetKeys: failedResults.map(result => result.key), settings: lastSettings });
  }

  function downloadFailures(data: BulkKeyUpdateResponse) {
    const failures = data.results.filter(result => !result.updated);
    const url = URL.createObjectURL(new Blob([JSON.stringify(failures, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "litegate-bulk-update-failures.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  const error = localError
    || (selectAll.error as Error | null)?.message
    || (update.error as Error | null)?.message;

  return (
    <details open={expanded ? true : undefined} onToggle={event => setEditorOpen(event.currentTarget.open)} className="w-full rounded-xl border border-[#2A2E42] bg-[#1A1D27]">
      <summary className="flex cursor-pointer list-none items-center gap-2 p-4 text-sm font-medium text-gray-200">
        <SlidersHorizontal size={16} /> Bulk edit key settings
        {targetCount > 0 && <span className="ml-auto rounded-full bg-indigo-500/15 px-2.5 py-1 text-[10px] font-semibold text-indigo-300">{targetCount} selected</span>}
      </summary>
      <form onSubmit={submit} className="grid gap-4 border-t border-[#2A2E42] p-4 sm:grid-cols-2">
        <div className="space-y-3 sm:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div><p className="text-xs font-semibold text-gray-200">1. Find and choose keys</p><p className="mt-0.5 text-[11px] text-gray-600">Search runs across the installation. Selections persist across pages.</p></div>
            {adminKeys.data && <span className="shrink-0 text-[10px] text-gray-500">{adminKeys.data.total} results</span>}
          </div>

          <div className="overflow-hidden rounded-xl border border-[#2A2E42] bg-[#0F1117]">
            <div className="space-y-3 border-b border-[#2A2E42] bg-[#151822] p-3">
              <div className="grid gap-2 sm:grid-cols-[1fr_12rem_9rem_auto]">
                <label className="relative">
                  <span className="sr-only">Search all keys</span>
                  <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
                  <input aria-label="Search all keys" value={searchInput} onChange={event => setSearchInput(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); applySearch(); } }} className={`${inputClass} w-full pl-9`} placeholder="User, alias, team, or key ID" />
                </label>
                <input aria-label="Filter by exact team ID" value={teamFilter} onChange={event => { setTeamFilter(event.target.value); setPage(1); selectAll.reset(); }} className={inputClass} placeholder="Exact team ID" />
                <select aria-label="Filter by blocked state" value={blockedFilter} onChange={event => { setBlockedFilter(event.target.value); setPage(1); selectAll.reset(); }} className={inputClass}><option value="">Any status</option><option value="false">Active only</option><option value="true">Blocked only</option></select>
                <button type="button" onClick={applySearch} className="rounded-lg bg-[#2A2E42] px-3 py-2 text-xs font-medium text-gray-200 hover:bg-[#353A52]">Search</button>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${selected.length ? "bg-indigo-500/15 text-indigo-300" : "bg-[#22263A] text-gray-500"}`}>{selected.length} selected</span>{hasFilters && <button type="button" onClick={clearFilters} className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-gray-500 hover:bg-[#22263A] hover:text-white"><X size={11} /> Clear filters</button>}</div>
                <div className="flex flex-wrap items-center gap-2">
                  {selected.length > 0 && <button type="button" onClick={() => setSelected([])} className="rounded-lg px-2.5 py-1.5 text-[11px] text-gray-400 hover:bg-[#22263A] hover:text-white">Clear selection</button>}
                  <button type="button" onClick={toggleAllKeys} disabled={!adminKeys.data?.total || selectAll.isPending} className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-2.5 py-1.5 text-[11px] font-medium text-cyan-300 hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-35">{selectAll.isPending ? "Selecting..." : allKeysSelected ? `Deselect all (${allFetchedTokens.length})` : `Select all ${hasFilters ? "results" : "keys"} (${adminKeys.data?.total ?? 0})`}</button>
                  <button type="button" onClick={toggleVisible} disabled={!visibleTokens.length} className="rounded-lg border border-indigo-500/25 bg-indigo-500/10 px-2.5 py-1.5 text-[11px] font-medium text-indigo-300 hover:bg-indigo-500/20 disabled:cursor-not-allowed disabled:opacity-35">{allVisibleSelected ? "Deselect page" : `Select page (${visibleTokens.length})`}</button>
                </div>
              </div>
            </div>

            {adminKeys.isLoading ? <div className="h-44 animate-pulse bg-[#22263A]" /> : adminKeys.error ? <p className="p-4 text-xs text-red-400">{(adminKeys.error as Error).message}</p> : visibleKeys.length ? <>
              <div className="max-h-96 space-y-2 overflow-y-auto p-2">
                {visibleKeys.map((key, index) => {
                  const token = keyToken(key);
                  const isSelected = Boolean(token && selected.includes(token));
                  const label = key.key_alias || `Key ${(adminKeys.data?.page ?? page) * 25 - 24 + index}`;
                  return <label key={token || index} className={`group flex items-center gap-3 rounded-lg border p-3 transition focus-within:ring-2 focus-within:ring-indigo-500/50 ${!token ? "cursor-not-allowed border-transparent opacity-40" : isSelected ? "cursor-pointer border-indigo-500/55 bg-indigo-500/10" : "cursor-pointer border-transparent bg-[#151822] hover:border-[#353A52] hover:bg-[#1A1D27]"}`}>
                    <input className="sr-only" type="checkbox" checked={isSelected} onChange={() => toggleKey(token)} disabled={!token} aria-label={`${isSelected ? "Deselect" : "Select"} ${label}`} />
                    <span aria-hidden="true" className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${isSelected ? "border-indigo-400 bg-indigo-500 text-white" : "border-gray-600 bg-[#0F1117] group-hover:border-indigo-400"}`}>{isSelected && <Check size={13} strokeWidth={3} />}</span>
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${isSelected ? "bg-indigo-500/20 text-indigo-300" : "bg-[#22263A] text-gray-500"}`}><KeyRound size={16} /></span>
                    <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium text-gray-200">{label}</span><span className="mt-0.5 block truncate font-mono text-[10px] text-gray-600">{maskedToken(token)}</span><span className="mt-1 flex min-w-0 items-center gap-1 text-[10px] text-gray-500"><UserRound size={10} className="shrink-0" /><span className="truncate">{key.user_email || key.user_id || "Unassigned user"}</span></span></span>
                    <span className="hidden shrink-0 flex-col items-end gap-1 sm:flex"><span className="rounded bg-[#22263A] px-2 py-0.5 text-[10px] text-gray-400">${(key.spend ?? 0).toFixed(2)} spent</span>{key.team_id && <span className="max-w-32 truncate rounded bg-cyan-500/10 px-2 py-0.5 text-[10px] text-cyan-300" title={key.team_id}>{key.team_id}</span>}</span>
                  </label>;
                })}
              </div>
              <div className="flex items-center justify-between border-t border-[#2A2E42] bg-[#151822] px-3 py-2.5 text-xs">
                <button type="button" onClick={() => setPage(value => Math.max(1, value - 1))} disabled={page <= 1 || adminKeys.isFetching} className="rounded px-2 py-1 text-gray-400 hover:bg-[#22263A] hover:text-white disabled:opacity-30">Previous</button>
                <span className="text-gray-600">Page {adminKeys.data?.page} of {adminKeys.data?.total_pages}{adminKeys.isFetching ? " · refreshing" : ""}</span>
                <button type="button" onClick={() => setPage(value => value + 1)} disabled={page >= (adminKeys.data?.total_pages ?? 1) || adminKeys.isFetching} className="rounded px-2 py-1 text-gray-400 hover:bg-[#22263A] hover:text-white disabled:opacity-30">Next</button>
              </div>
            </> : <p className="p-8 text-center text-xs text-gray-500">{hasFilters ? "No keys match these installation-wide filters." : "No keys found."}</p>}
          </div>

          <details className="rounded-lg border border-dashed border-[#2A2E42] px-3 py-2.5"><summary className="cursor-pointer text-[11px] text-gray-500 hover:text-gray-300">Advanced: paste key IDs manually</summary><label className={`${fieldClass} mt-3 block`}><span>Key IDs, one per line</span><textarea className={`${inputClass} mt-1 min-h-20 w-full`} value={targets} onChange={event => setTargets(event.target.value)} /></label></details>
        </div>

        <div className="sm:col-span-2"><p className="text-xs font-semibold text-gray-200">2. Choose settings to change</p><p className="mt-0.5 text-[11px] text-gray-600">Only filled fields are changed. Empty fields leave existing values untouched.</p></div>
        <label className={fieldClass}><span>Alias</span><input className={`${inputClass} w-full`} value={alias} onChange={event => setAlias(event.target.value)} placeholder="No change" /></label>
        <label className={fieldClass}><span>Allowed models</span><input className={`${inputClass} w-full`} value={models} onChange={event => setModels(event.target.value)} placeholder="Comma-separated; no change when empty" /></label>
        <label className={fieldClass}><span>Maximum budget</span><input className={`${inputClass} w-full`} value={budget} onChange={event => setBudget(event.target.value)} type="number" min="0" step="any" placeholder="No change" /></label>
        <label className={fieldClass}><span>Budget reset</span><input className={`${inputClass} w-full`} value={budgetDuration} onChange={event => setBudgetDuration(event.target.value)} placeholder="For example 30d" /></label>
        <label className={fieldClass}><span>TPM limit</span><input className={`${inputClass} w-full`} value={tpm} onChange={event => setTpm(event.target.value)} type="number" min="0" placeholder="No change" /></label>
        <label className={fieldClass}><span>RPM limit</span><input className={`${inputClass} w-full`} value={rpm} onChange={event => setRpm(event.target.value)} type="number" min="0" placeholder="No change" /></label>
        <label className={fieldClass}><span>New duration</span><input className={`${inputClass} w-full`} value={duration} onChange={event => setDuration(event.target.value)} placeholder="For example 90d" /></label>
        <label className={fieldClass}><span>Blocked state</span><select className={`${inputClass} w-full`} value={blockedSetting} onChange={event => setBlockedSetting(event.target.value)}><option value="">No change</option><option value="false">Unblock</option><option value="true">Block</option></select></label>

        {error && <p className="text-xs text-red-400 sm:col-span-2">{error}</p>}
        {operationsBlocked && <p className="text-xs text-amber-300 sm:col-span-2">Bulk updates are paused. Try again in {retryAfter || 1} seconds.</p>}
        {update.data && <div className={`rounded-lg border p-3 text-xs sm:col-span-2 ${update.data.failed ? "border-amber-500/25 bg-amber-500/5 text-amber-200" : "border-green-500/25 bg-green-500/5 text-green-300"}`}><div className="flex flex-wrap items-center justify-between gap-2"><span>{update.data.updated} updated, {update.data.failed} failed.</span>{update.data.failed > 0 && <div className="flex gap-2"><button type="button" onClick={retryFailures} disabled={update.isPending || operationsBlocked} className="rounded border border-amber-500/30 px-2 py-1 hover:bg-amber-500/10 disabled:opacity-40">Retry failed</button><button type="button" onClick={() => downloadFailures(update.data!)} className="flex items-center gap-1 rounded border border-amber-500/30 px-2 py-1 hover:bg-amber-500/10"><Download size={11} /> Download failures</button></div>}</div>{failedResults.length > 0 && <ul className="mt-2 max-h-28 space-y-1 overflow-y-auto font-mono text-[10px] text-amber-100/70">{failedResults.map(result => <li key={result.key} className="truncate" title={result.error}>{maskedToken(result.key)} - {result.error || "Update failed"}</li>)}</ul>}</div>}
        <button disabled={update.isPending || operationsBlocked || targetCount === 0} className="rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-950/30 hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2">{update.isPending ? "Updating..." : operationsBlocked ? "Bulk updates paused" : targetCount ? `Apply settings to ${targetCount} ${targetCount === 1 ? "key" : "keys"}` : "Select keys to continue"}</button>
      </form>
    </details>
  );
}
