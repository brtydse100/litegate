import { useMemo, useRef, useState } from "react";
import AdvancedPolicySettings, {
  type AdvancedPolicyHandle,
} from "./AdvancedPolicySettings";
import EmailAddress from "./EmailAddress";
import { Pill, UsageBar } from "./Page";
import { isKeyExpired } from "../keyBudget";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  Download,
  KeyRound,
  RotateCcw,
  Search,
  SlidersHorizontal,
  UserRound,
  X,
} from "lucide-react";
import { api } from "../api/client";
import RevealKey from "./RevealKey";
import ModelBudgetEditor, {
  parseModelBudgets,
  type ModelBudgetRow,
} from "./ModelBudgetEditor";
import {
  CurrentPolicySettings,
  DurationChoices,
  ModelChoices,
  NumericPolicyInput,
} from "./PolicySettings";
import { useDialogDismiss } from "../hooks/useDialogDismiss";
import { useOperationLimit } from "../hooks/useOperationLimit";
import { metricValue } from "./OrganizationCharts";
import { useKeySettingsForm } from "../hooks/useKeySettingsForm";
import type {
  AdminKeyFilters,
  BulkKeySpendResetResponse,
  BulkKeyUpdateResponse,
  KeyInfo,
  KeySettingsUpdate,
} from "../types";

const inputClass =
  "rounded-md border border-line-input bg-card px-3 py-2 text-sm text-ink shadow-sm placeholder:text-ink-4 focus:border-blue focus:outline-none focus:ring-2 focus:ring-blue/20";
const fieldClass = "space-y-1 text-xs text-ink-3";
const emptyKeys: KeyInfo[] = [];
const emptyTokens: string[] = [];

interface ResetTarget {
  keys: string[];
}

export function keyToken(key: KeyInfo): string {
  return key.token ?? key.api_key ?? key.key ?? "";
}

export function maskedToken(token: string): string {
  if (!token) return "Key identifier unavailable";
  if (token.length <= 16) return token;
  return `${token.slice(0, 9)}....${token.slice(-4)}`;
}

export default function BulkKeyEditor({
  expanded = false,
  saveApiKeysInDb = false,
  enterpriseEnabled = false,
}: {
  expanded?: boolean;
  saveApiKeysInDb?: boolean;
  enterpriseEnabled?: boolean;
}) {
  const queryClient = useQueryClient();
  const advanced = useRef<AdvancedPolicyHandle>(null);
  const { operationsBlocked, retryAfter, refreshOperationLimit } =
    useOperationLimit();
  const [editorOpen, setEditorOpen] = useState(expanded);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [blockedFilter, setBlockedFilter] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const selectionId = useMemo(() => JSON.stringify(selected), [selected]);
  const [modelBudgetDraft, setModelBudgetDraft] = useState<{
    selection: string;
    rows: ModelBudgetRow[] | undefined;
  }>();
  if (modelBudgetDraft && modelBudgetDraft.selection !== selectionId)
    setModelBudgetDraft(undefined);
  const modelBudgetRows =
    modelBudgetDraft?.selection === selectionId
      ? modelBudgetDraft.rows
      : undefined;
  const [useKeyBudgetOnly, setUseKeyBudgetOnly] = useState(false);
  const [lastUseKeyBudgetOnly, setLastUseKeyBudgetOnly] = useState(false);
  const [localError, setLocalError] = useState("");
  const [resetTarget, setResetTarget] = useState<ResetTarget | null>(null);
  const [lastSettings, setLastSettings] = useState<KeySettingsUpdate | null>(
    null,
  );

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
    placeholderData: (previous) => previous,
  });

  const selectAll = useMutation({
    mutationFn: () => api.listAllKeyIdentifiers(filters),
    onSuccess: (data) => {
      setSelected(data.keys);
      setLocalError("");
    },
  });

  const update = useMutation({
    onError: (error) => advanced.current?.setServerError(error),
    mutationFn: ({
      targetKeys,
      settings,
      keyBudgetOnly = false,
    }: {
      targetKeys: string[];
      settings: KeySettingsUpdate;
      keyBudgetOnly?: boolean;
    }) =>
      keyBudgetOnly
        ? api.bulkUpdateKeys(targetKeys, settings, true)
        : api.bulkUpdateKeys(targetKeys, settings),
    onSuccess: (data) => {
      const failedKeys = data.results
        .filter((result) => !result.updated)
        .map((result) => result.key);
      setSelected(failedKeys);
      if (!failedKeys.length) selectAll.reset();
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-keys"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-events"] });
    },
    onSettled: refreshOperationLimit,
  });

  const resetSpend = useMutation({
    mutationFn: (keys: string[]) => api.resetKeySpend(keys),
    onSuccess: (data) => {
      const failedKeys = data.results
        .filter((result) => !result.reset)
        .map((result) => result.key);
      setSelected(failedKeys);
      if (!failedKeys.length) selectAll.reset();
      setResetTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-keys"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-events"] });
    },
    onSettled: refreshOperationLimit,
  });

  const visibleKeys = adminKeys.data?.keys ?? emptyKeys;
  const visibleTokens = visibleKeys.map(keyToken).filter(Boolean);
  const selectedVisibleKeys = useMemo(
    () => visibleKeys.filter((key) => selectedSet.has(keyToken(key))),
    [visibleKeys, selectedSet],
  );
  const {
    values,
    setValue,
    isChanged,
    placeholder,
    modelSelection,
    setModels,
    modelsChanged,
    modelStatus,
  } = useKeySettingsForm(selected, selectedVisibleKeys);
  const { alias, budget, budgetDuration, tpm, rpm, duration, blockedSetting } =
    values;
  const allVisibleSelected =
    visibleTokens.length > 0 &&
    visibleTokens.every((token) => selectedSet.has(token));
  const allFetchedTokens = selectAll.data?.keys ?? emptyTokens;
  const allKeysSelected = useMemo(
    () =>
      allFetchedTokens.length > 0 &&
      selectAll.data?.total === adminKeys.data?.total &&
      allFetchedTokens.every((token) => selectedSet.has(token)),
    [
      allFetchedTokens,
      selectAll.data?.total,
      adminKeys.data?.total,
      selectedSet,
    ],
  );
  const targetKeys = selected;
  const targetCount = targetKeys.length;
  const failedResults =
    update.data?.results.filter((result) => !result.updated) ?? [];
  const failedResetResults =
    resetSpend.data?.results.filter((result) => !result.reset) ?? [];

  function settingsFromForm(): KeySettingsUpdate {
    const settings: KeySettingsUpdate = {};
    const advancedSettings = advanced.current?.read() ?? {};
    if (Object.keys(advancedSettings).length)
      settings.advanced_settings = advancedSettings;
    if (enterpriseEnabled && modelBudgetRows !== undefined)
      settings.model_max_budget = parseModelBudgets(modelBudgetRows);
    if (isChanged("alias") && alias.trim()) settings.key_alias = alias.trim();
    if (modelsChanged)
      settings.models = modelSelection.all ? [] : modelSelection.models;
    if (isChanged("budget") && budget !== "")
      settings.max_budget = Number(budget);
    if (isChanged("budgetDuration") && budgetDuration.trim())
      settings.budget_duration = budgetDuration.trim();
    if (isChanged("tpm") && tpm !== "") settings.tpm_limit = Number(tpm);
    if (isChanged("rpm") && rpm !== "") settings.rpm_limit = Number(rpm);
    if (isChanged("duration") && duration.trim())
      settings.duration = duration.trim();
    if (isChanged("blockedSetting") && blockedSetting !== "")
      settings.blocked = blockedSetting === "true";
    return settings;
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (operationsBlocked || update.isPending) return;
    setLocalError("");
    if (!targetKeys.length) {
      setLocalError("Select at least one key to update.");
      return;
    }
    if (modelsChanged && !modelSelection.all && !modelSelection.models.length) {
      setLocalError("Select at least one model or allow all models.");
      return;
    }
    let settings: KeySettingsUpdate;
    try {
      settings = settingsFromForm();
    } catch (error) {
      setLocalError((error as Error).message);
      return;
    }
    if (!Object.keys(settings).length && !useKeyBudgetOnly) {
      setLocalError("Choose at least one setting to change.");
      return;
    }
    setLastSettings(settings);
    setLastUseKeyBudgetOnly(useKeyBudgetOnly);
    update.mutate({ targetKeys, settings, keyBudgetOnly: useKeyBudgetOnly });
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
    setSelected((current) =>
      current.includes(token)
        ? current.filter((value) => value !== token)
        : [...current, token],
    );
  }

  function toggleVisible() {
    setSelected((current) =>
      allVisibleSelected
        ? current.filter((token) => !visibleTokens.includes(token))
        : Array.from(new Set([...current, ...visibleTokens])),
    );
  }

  function toggleAllKeys() {
    if (allKeysSelected) {
      const allTokenSet = new Set(allFetchedTokens);
      setSelected((current) =>
        current.filter((token) => !allTokenSet.has(token)),
      );
      return;
    }
    setLocalError("");
    selectAll.mutate();
  }

  function retryFailures() {
    if (
      !lastSettings ||
      !failedResults.length ||
      operationsBlocked ||
      update.isPending
    )
      return;
    update.mutate({
      targetKeys: failedResults.map((result) => result.key),
      settings: lastSettings,
      keyBudgetOnly: lastUseKeyBudgetOnly,
    });
  }

  function openResetDialog() {
    if (!targetKeys.length || operationsBlocked) return;
    resetSpend.reset();
    setResetTarget({ keys: targetKeys });
  }

  function retryResetFailures() {
    if (!failedResetResults.length || operationsBlocked || resetSpend.isPending)
      return;
    resetSpend.mutate(failedResetResults.map((result) => result.key));
  }

  function downloadFailures(data: BulkKeyUpdateResponse) {
    const failures = data.results.filter((result) => !result.updated);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(failures, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "litegate-bulk-update-failures.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadResetFailures(data: BulkKeySpendResetResponse) {
    const failures = data.results.filter((result) => !result.reset);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(failures, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "litegate-spend-reset-failures.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  const error =
    localError ||
    (selectAll.error as Error | null)?.message ||
    (update.error as Error | null)?.message;

  return (
    <details
      open={expanded ? true : undefined}
      onToggle={(event) => setEditorOpen(event.currentTarget.open)}
      className="w-full rounded-xl border border-line bg-card"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-3.5 text-base font-bold text-ink">
        <SlidersHorizontal size={16} /> Bulk edit key settings
        {targetCount > 0 && (
          <span className="ml-auto rounded-full bg-blue-tint px-2.5 py-1 text-[10px] font-semibold text-blue-ink">
            {targetCount} selected
          </span>
        )}
      </summary>
      <form
        onSubmit={submit}
        className="grid gap-4 border-t border-line p-4 sm:grid-cols-2"
      >
        <DurationChoices id="key-budget-durations" />
        <DurationChoices id="key-lifetime-durations" />
        <div className="space-y-3 sm:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold text-ink">
                Find and choose keys
              </p>
              <p className="mt-0.5 text-[11px] text-ink-4">
                Search runs across the installation. Selections persist across
                pages.
              </p>
            </div>
            {adminKeys.data && (
              <span className="shrink-0 text-[10px] text-ink-4">
                {adminKeys.data.total} results
              </span>
            )}
          </div>

          <div className="overflow-hidden rounded-xl border border-line bg-card">
            <div className="space-y-3 border-b border-line bg-canvas p-3">
              <div className="grid gap-2 sm:grid-cols-[1fr_12rem_9rem_auto]">
                <label className="relative">
                  <span className="sr-only">Search all keys</span>
                  <Search
                    size={14}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-4"
                  />
                  <input
                    aria-label="Search all keys"
                    value={searchInput}
                    onChange={(event) => setSearchInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        applySearch();
                      }
                    }}
                    className={`${inputClass} w-full pl-9`}
                    placeholder="User, alias, team, or key ID"
                  />
                </label>
                <input
                  aria-label="Filter by exact team ID"
                  value={teamFilter}
                  onChange={(event) => {
                    setTeamFilter(event.target.value);
                    setPage(1);
                    selectAll.reset();
                  }}
                  className={inputClass}
                  placeholder="Exact team ID"
                />
                <select
                  aria-label="Filter by blocked state"
                  value={blockedFilter}
                  onChange={(event) => {
                    setBlockedFilter(event.target.value);
                    setPage(1);
                    selectAll.reset();
                  }}
                  className={inputClass}
                >
                  <option value="">Any status</option>
                  <option value="false">Active only</option>
                  <option value="true">Blocked only</option>
                </select>
                <button
                  type="button"
                  onClick={applySearch}
                  className="rounded-lg bg-line px-3 py-2 text-xs font-medium text-ink hover:bg-line-input"
                >
                  Search
                </button>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${selected.length ? "bg-blue-tint text-blue-ink" : "bg-canvas text-ink-4"}`}
                  >
                    {selected.length} selected
                  </span>
                  {hasFilters && (
                    <button
                      type="button"
                      onClick={clearFilters}
                      className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-ink-4 hover:bg-canvas hover:text-ink"
                    >
                      <X size={11} /> Clear filters
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {selected.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelected([])}
                      className="rounded-lg px-2.5 py-1.5 text-[11px] text-ink-3 hover:bg-canvas hover:text-ink"
                    >
                      Clear selection
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={toggleAllKeys}
                    disabled={!adminKeys.data?.total || selectAll.isPending}
                    className="rounded-lg border border-cyan/40 bg-cyan-tint px-2.5 py-1.5 text-[11px] font-medium text-cyan-ink hover:border-cyan disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    {selectAll.isPending
                      ? "Selecting..."
                      : allKeysSelected
                        ? `Deselect all (${allFetchedTokens.length})`
                        : `Select all ${hasFilters ? "results" : "keys"} (${adminKeys.data?.total ?? 0})`}
                  </button>
                  <button
                    type="button"
                    onClick={toggleVisible}
                    disabled={!visibleTokens.length}
                    className="rounded-lg border border-blue/30 bg-blue-tint px-2.5 py-1.5 text-[11px] font-medium text-blue-ink hover:border-blue disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    {allVisibleSelected
                      ? "Deselect page"
                      : `Select page (${visibleTokens.length})`}
                  </button>
                </div>
              </div>
            </div>

            {adminKeys.isLoading ? (
              <div className="h-44 animate-pulse bg-canvas" />
            ) : adminKeys.error ? (
              <p className="p-4 text-xs text-danger">
                {(adminKeys.error as Error).message}
              </p>
            ) : visibleKeys.length ? (
              <>
                <div className="overflow-x-auto">
                  <div className="min-w-[860px] space-y-1 p-2">
                    {visibleKeys.map((key, index) => {
                      const token = keyToken(key);
                      const isSelected = Boolean(
                        token && selectedSet.has(token),
                      );
                      const label =
                        key.key_alias ||
                        `Key ${(adminKeys.data?.page ?? page) * 25 - 24 + index}`;
                      return (
                        <div
                          key={token || index}
                          className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 rounded-lg border px-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue/50 ${!token ? "opacity-40" : isSelected ? "border-blue/60 bg-blue-tint/60" : "border-transparent hover:border-line hover:bg-canvas"}`}
                        >
                          <label
                            className={`group grid min-w-0 grid-cols-[auto_minmax(0,2fr)_minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1.2fr)_auto] items-center gap-3 py-2.5 transition ${!token ? "cursor-not-allowed" : "cursor-pointer"}`}
                          >
                            <input
                              className="sr-only"
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleKey(token)}
                              disabled={!token}
                              aria-label={`${isSelected ? "Deselect" : "Select"} ${label}`}
                            />
                            <span
                              aria-hidden="true"
                              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${isSelected ? "border-blue bg-blue text-paper" : "border-line-input bg-card group-hover:border-blue/60"}`}
                            >
                              {isSelected && (
                                <Check size={13} strokeWidth={3} />
                              )}
                            </span>
                            <span className="flex min-w-0 items-center gap-2.5">
                              <span
                                aria-hidden="true"
                                className={`hidden h-8 w-8 shrink-0 items-center justify-center rounded-lg sm:flex ${isSelected ? "bg-blue text-paper" : "bg-blue-tint text-blue-ink"}`}
                              >
                                <KeyRound size={15} />
                              </span>
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-semibold text-ink">
                                  {label}
                                </span>
                                <span className="block truncate font-mono text-xs text-ink-4">
                                  {maskedToken(token)}
                                </span>
                              </span>
                            </span>
                            <span className="flex min-w-0 items-center gap-1.5 text-[13px] text-ink-3">
                              <UserRound
                                size={13}
                                aria-hidden="true"
                                className="shrink-0 text-ink-4"
                              />
                              {key.user_email ? (
                                <EmailAddress email={key.user_email} />
                              ) : (
                                <span className="break-all">
                                  {key.user_id || "Unassigned user"}
                                </span>
                              )}
                            </span>
                            <span className="min-w-0">
                              {key.team_id ? (
                                <span
                                  className="inline-block max-w-full truncate rounded-md bg-cyan-tint px-2 py-0.5 text-xs font-medium text-cyan-ink"
                                  title={key.team_id}
                                >
                                  {key.team_id}
                                </span>
                              ) : (
                                <span className="text-xs text-ink-4">
                                  No team
                                </span>
                              )}
                            </span>
                            <span className="flex min-w-0 flex-col gap-1.5">
                              <span className="text-[13px] text-ink-2">
                                <span>
                                  {metricValue(key.spend ?? 0, "spend")} spent
                                </span>
                                {key.max_budget != null && (
                                  <span className="text-ink-4">
                                    {" "}
                                    of {metricValue(key.max_budget, "spend")}
                                  </span>
                                )}
                              </span>
                              {key.max_budget ? (
                                <UsageBar
                                  percent={
                                    ((key.spend ?? 0) / key.max_budget) * 100
                                  }
                                />
                              ) : null}
                            </span>
                            <span className="justify-self-end">
                              {key.blocked ? (
                                <Pill tone="bad">Blocked</Pill>
                              ) : isKeyExpired(key.expires) ? (
                                <Pill tone="bad">Expired</Pill>
                              ) : (
                                <Pill tone="ok">Active</Pill>
                              )}
                            </span>
                          </label>
                          {saveApiKeysInDb && key.secret_available && (
                            <RevealKey
                              identifier={token}
                              compact
                              buttonClassName="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium text-blue-ink hover:bg-blue-tint disabled:opacity-50"
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
                <div className="flex items-center justify-between border-t border-line bg-canvas px-3 py-2.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setPage((value) => Math.max(1, value - 1))}
                    disabled={page <= 1 || adminKeys.isFetching}
                    className="rounded px-2 py-1 text-ink-3 hover:bg-well hover:text-ink disabled:opacity-30"
                  >
                    Previous
                  </button>
                  <span className="text-ink-4">
                    Page {adminKeys.data?.page} of {adminKeys.data?.total_pages}
                    {adminKeys.isFetching ? " · refreshing" : ""}
                  </span>
                  <button
                    type="button"
                    onClick={() => setPage((value) => value + 1)}
                    disabled={
                      page >= (adminKeys.data?.total_pages ?? 1) ||
                      adminKeys.isFetching
                    }
                    className="rounded px-2 py-1 text-ink-3 hover:bg-well hover:text-ink disabled:opacity-30"
                  >
                    Next
                  </button>
                </div>
              </>
            ) : (
              <p className="p-8 text-center text-xs text-ink-4">
                {hasFilters
                  ? "No keys match these installation-wide filters."
                  : "No keys found."}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sand/40 bg-sand-tint p-3">
            <div>
              <p className="text-xs font-medium text-sand-ink">
                Reset accumulated spend
              </p>
              <p className="mt-0.5 text-[11px] text-ink-4">
                Select one or more keys. Their budgets, limits, and spend
                histories are kept.
              </p>
            </div>
            <button
              type="button"
              onClick={openResetDialog}
              disabled={!targetCount || operationsBlocked}
              className="flex items-center gap-1.5 rounded-lg border border-sand/40 px-3 py-2 text-xs font-medium text-sand-ink hover:bg-sand-tint disabled:cursor-not-allowed disabled:opacity-40"
            >
              <RotateCcw size={13} />
              {targetCount
                ? `Reset spend for ${targetCount} ${targetCount === 1 ? "key" : "keys"}`
                : "Reset selected key spend"}
            </button>
          </div>
          {resetSpend.data && (
            <div
              className={`rounded-lg border p-3 text-xs ${resetSpend.data.failed ? "border-sand/40 bg-sand-tint text-sand-ink" : "border-mint/40 bg-mint-tint text-mint-ink"}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {resetSpend.data.reset} reset, {resetSpend.data.failed}{" "}
                  failed.
                </span>
                {resetSpend.data.failed > 0 && (
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={retryResetFailures}
                      disabled={resetSpend.isPending || operationsBlocked}
                      className="rounded border border-sand/40 px-2 py-1 hover:bg-sand-tint disabled:opacity-40"
                    >
                      Retry failed
                    </button>
                    <button
                      type="button"
                      onClick={() => downloadResetFailures(resetSpend.data!)}
                      className="flex items-center gap-1 rounded border border-sand/40 px-2 py-1 hover:bg-sand-tint"
                    >
                      <Download size={11} /> Download failures
                    </button>
                  </div>
                )}
              </div>
              {failedResetResults.length > 0 && (
                <ul className="mt-2 max-h-28 space-y-1 overflow-y-auto font-mono text-[10px] text-sand-ink">
                  {failedResetResults.map((result) => (
                    <li
                      key={result.key}
                      className="truncate"
                      title={result.error}
                    >
                      {maskedToken(result.key)} -{" "}
                      {result.error || "Reset failed"}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {targetCount > 0 && (
          <section
            aria-label="Current key settings"
            className="space-y-3 rounded-lg border border-line p-3 sm:col-span-2"
          >
            <h3 className="text-sm font-semibold text-ink">
              Current key settings
            </h3>
            {visibleKeys
              .filter((key) => selected.includes(keyToken(key)))
              .map((key) => (
                <div
                  key={keyToken(key)}
                  className="space-y-2 border-t border-line pt-2"
                >
                  <p className="text-xs font-medium text-ink-2">
                    {key.key_alias || maskedToken(keyToken(key))}
                  </p>
                  <CurrentPolicySettings settings={key} />
                </div>
              ))}
            {targetCount >
              visibleTokens.filter((token) => selectedSet.has(token))
                .length && (
              <p className="text-xs text-sand-ink">
                {targetCount -
                  visibleTokens.filter((token) => selectedSet.has(token))
                    .length}{" "}
                selected{" "}
                {targetCount -
                  visibleTokens.filter((token) => selectedSet.has(token))
                    .length ===
                1
                  ? "key is"
                  : "keys are"}{" "}
                on another page. View that page to inspect their current
                settings.
              </p>
            )}
          </section>
        )}
        {targetCount > 0 && (
          <details
            key={selectionId}
            open={targetCount > 0}
            className="group rounded-lg border border-line sm:col-span-2"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 p-3 text-xs font-semibold text-ink-2">
              <span>Choose settings to change</span>
              <ChevronDown
                size={16}
                aria-hidden="true"
                className="transition-transform group-open:rotate-180"
              />
            </summary>
            <div className="grid gap-4 border-t border-line p-3 sm:grid-cols-2">
              <p className="text-[11px] text-ink-4 sm:col-span-2">
                Saved values are filled in below. Only edited, filled fields are
                changed. Mixed values differ between selected keys. Changing the
                selection resets edits.
              </p>
              <label className={fieldClass}>
                <span>Alias</span>
                <input
                  className={`${inputClass} w-full`}
                  value={alias}
                  onChange={(event) => setValue("alias", event.target.value)}
                  placeholder={placeholder("alias")}
                />
              </label>
              <ModelChoices
                scrollable={false}
                value={modelSelection}
                onChange={setModels}
                knownModels={selectedVisibleKeys.flatMap(
                  (key) => key.models ?? [],
                )}
                status={modelStatus}
              />
              {enterpriseEnabled && (
                <ModelBudgetEditor
                  rows={modelBudgetRows}
                  onChange={(rows) =>
                    setModelBudgetDraft({ selection: selectionId, rows })
                  }
                  saved={
                    selected.length === 1
                      ? selectedVisibleKeys[0]?.model_max_budget
                      : undefined
                  }
                />
              )}
              <NumericPolicyInput
                label="Maximum budget"
                value={budget}
                onValueChange={(value) => setValue("budget", value)}
                step="any"
                placeholder={placeholder("budget")}
              />
              <label className={fieldClass}>
                <span>Budget reset</span>
                <input
                  className={`${inputClass} w-full`}
                  value={budgetDuration}
                  list="key-budget-durations"
                  onChange={(event) =>
                    setValue("budgetDuration", event.target.value)
                  }
                  placeholder={placeholder("budgetDuration")}
                />
              </label>
              <NumericPolicyInput
                label="TPM limit"
                value={tpm}
                onValueChange={(value) => setValue("tpm", value)}
                placeholder={placeholder("tpm")}
              />
              <NumericPolicyInput
                label="RPM limit"
                value={rpm}
                onValueChange={(value) => setValue("rpm", value)}
                placeholder={placeholder("rpm")}
              />
              <label className={fieldClass}>
                <span>New duration</span>
                <input
                  className={`${inputClass} w-full`}
                  value={duration}
                  list="key-lifetime-durations"
                  onChange={(event) => setValue("duration", event.target.value)}
                  placeholder="For example 90d"
                />
              </label>
              <label className={fieldClass}>
                <span>Blocked state</span>
                <select
                  className={`${inputClass} w-full`}
                  value={blockedSetting}
                  onChange={(event) =>
                    setValue("blockedSetting", event.target.value)
                  }
                >
                  <option value="">{placeholder("blockedSetting")}</option>
                  <option value="false">Unblock</option>
                  <option value="true">Block</option>
                </select>
              </label>

              <div className="space-y-1 sm:col-span-2">
                <label className="flex items-center gap-2 text-xs text-ink-3">
                  <input
                    type="checkbox"
                    checked={useKeyBudgetOnly}
                    onChange={(event) =>
                      setUseKeyBudgetOnly(event.target.checked)
                    }
                  />
                  Use key budget as the individual allowance
                </label>
                <p className="text-xs text-ink-4">
                  Requires one key per owner with a finite budget. Removes the
                  owner's separate personal budget and member budget in this
                  key's team. Shared team budgets remain in force. Key settings
                  may be saved even if removing a user budget fails; failures
                  can be retried.
                </p>
              </div>
              <AdvancedPolicySettings
                key={selectionId}
                ref={advanced}
                operation="key_update"
                excludedFields={[
                  "key_alias",
                  "models",
                  "max_budget",
                  "budget_duration",
                  "tpm_limit",
                  "rpm_limit",
                  "duration",
                  "blocked",
                  "model_max_budget",
                ]}
                current={
                  selected.length === 1
                    ? {
                        ...selectedVisibleKeys[0],
                        ...selectedVisibleKeys[0]?.advanced_settings,
                      }
                    : undefined
                }
              />
              <button
                disabled={
                  update.isPending || operationsBlocked || targetCount === 0
                }
                className="rounded-lg bg-blue px-4 py-3 text-sm font-semibold text-paper shadow-lg hover:brightness-90 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2"
              >
                {update.isPending
                  ? "Updating..."
                  : operationsBlocked
                    ? "Bulk updates paused"
                    : targetCount
                      ? `Apply settings to ${targetCount} ${targetCount === 1 ? "key" : "keys"}`
                      : "Select keys to continue"}
              </button>
            </div>
          </details>
        )}
        {error && <p className="text-xs text-danger sm:col-span-2">{error}</p>}
        {operationsBlocked && (
          <p className="text-xs text-sand-ink sm:col-span-2">
            Bulk updates are paused. Try again in {retryAfter || 1} seconds.
          </p>
        )}
        {update.data && (
          <div
            className={`rounded-lg border p-3 text-xs sm:col-span-2 ${update.data.failed ? "border-sand/40 bg-sand-tint text-sand-ink" : "border-mint/40 bg-mint-tint text-mint-ink"}`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {update.data.updated} updated, {update.data.failed} failed.
              </span>
              {update.data.failed > 0 && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={retryFailures}
                    disabled={update.isPending || operationsBlocked}
                    className="rounded border border-sand/40 px-2 py-1 hover:bg-sand-tint disabled:opacity-40"
                  >
                    Retry failed
                  </button>
                  <button
                    type="button"
                    onClick={() => downloadFailures(update.data!)}
                    className="flex items-center gap-1 rounded border border-sand/40 px-2 py-1 hover:bg-sand-tint"
                  >
                    <Download size={11} /> Download failures
                  </button>
                </div>
              )}
            </div>
            {failedResults.length > 0 && (
              <ul className="mt-2 max-h-28 space-y-1 overflow-y-auto font-mono text-[10px] text-sand-ink">
                {failedResults.map((result) => (
                  <li
                    key={result.key}
                    className="truncate"
                    title={result.error}
                  >
                    {maskedToken(result.key)} -{" "}
                    {result.error || "Update failed"}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </form>
      {resetTarget && (
        <ResetSpendDialog
          target={resetTarget}
          pending={resetSpend.isPending}
          operationsBlocked={operationsBlocked}
          error={(resetSpend.error as Error | null)?.message}
          onClose={() => {
            if (!resetSpend.isPending) {
              setResetTarget(null);
              resetSpend.reset();
            }
          }}
          onReset={() => resetSpend.mutate(resetTarget.keys)}
        />
      )}
    </details>
  );
}

function ResetSpendDialog({
  target,
  pending,
  operationsBlocked,
  error,
  onClose,
  onReset,
}: {
  target: ResetTarget;
  pending: boolean;
  operationsBlocked: boolean;
  error?: string;
  onClose: () => void;
  onReset: () => void;
}) {
  const dialogRef = useDialogDismiss(onClose, pending);
  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      ref={dialogRef}
      aria-modal="true"
      aria-labelledby="reset-spend-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-sand/40 bg-card p-5 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-sand-tint p-2 text-sand-ink">
            <RotateCcw size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <h3 id="reset-spend-title" className="font-semibold text-ink">
              Reset spend for {target.keys.length}{" "}
              {target.keys.length === 1 ? "key" : "keys"}?
            </h3>
            <p className="mt-1 text-xs leading-5 text-ink-3">
              Accumulated spend will be reset to $0.00. LiteLLM keeps each key's
              spend logs, budget, and limits.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            aria-label="Close reset spend dialog"
            className="text-ink-4 hover:text-ink disabled:opacity-40"
          >
            <X size={18} />
          </button>
        </div>
        {error && <p className="mt-3 text-xs text-danger">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded-lg border border-line px-4 py-2 text-sm text-ink-2 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={pending || operationsBlocked}
            className="rounded-lg bg-sand-solid px-4 py-2 text-sm font-semibold text-paper hover:brightness-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {pending
              ? "Resetting..."
              : operationsBlocked
                ? "Key actions paused"
                : "Reset spend to zero"}
          </button>
        </div>
      </div>
    </div>
  );
}
