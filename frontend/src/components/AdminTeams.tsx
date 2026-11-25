import { useEffect, useRef, useState } from "react";
import AdvancedPolicySettings, {
  type AdvancedPolicyHandle,
} from "./AdvancedPolicySettings";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Edit3,
  Plus,
  Search,
  ShieldAlert,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { api } from "../api/client";
import { useDialogDismiss } from "../hooks/useDialogDismiss";
import { useOperationLimit } from "../hooks/useOperationLimit";
import type {
  BudgetWindowSchedule,
  TeamCreatePayload,
  TeamInfo,
  TeamUpdatePayload,
  ModelSelection,
} from "../types";
import TeamMembersDialog from "./TeamMembersDialog";
import DismissibleMessage from "./DismissibleMessage";
import { Callout, PageHeader, Pill, UsageBar } from "./Page";
import {
  buttonCreate,
  buttonSecondary,
  buttonSmall,
  buttonSmallDanger,
  card,
  cardHeader,
  cardTitle,
  fieldInput,
  tableHead,
} from "./ui";

/** Team list columns, shared by the caption row and each team. */
const teamColumns =
  "grid min-w-[976px] grid-cols-[minmax(0,2.2fr)_minmax(0,1.5fr)_minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,0.9fr)_17rem] items-center gap-4";
import { metricValue } from "./OrganizationCharts";
import { resetLabel } from "../keyBudget";
import {
  BudgetWindowsBanner,
  TeamWindowUsage,
  WindowBudgetFields,
  choicePayload,
  initialChoices,
  type WindowChoice,
} from "./BudgetWindows";
import {
  CurrentPolicySettings,
  DurationChoices,
  ModelChoices,
  NumericPolicyInput,
} from "./PolicySettings";

const inputClass =
  "w-full rounded-md border border-line-input bg-card px-3 py-2 text-sm text-ink shadow-sm placeholder:text-ink-4 focus:border-blue focus:outline-none focus:ring-2 focus:ring-blue/20";

type EditorState = { mode: "create" } | { mode: "edit"; team: TeamInfo };

function optionalNumber(value: string): number | undefined {
  return value === "" ? undefined : Number(value);
}

function nullableNumber(value: string): number | null {
  return value === "" ? null : Number(value);
}

function currentLimitPlaceholder(value: number | null | undefined): string {
  return value === undefined
    ? "Not provided"
    : value === null
      ? "Unlimited"
      : String(value);
}

function TeamEditor({
  state,
  pending,
  operationsBlocked,
  error,
  onClose,
  onCreate,
  onUpdate,
  budgetWindows,
}: {
  state: EditorState;
  pending: boolean;
  operationsBlocked: boolean;
  /** TEAM_BUDGET_WINDOWS: the schedule every team shares (nightly). */
  budgetWindows?: BudgetWindowSchedule | null;
  error?: Error | null;
  onClose: () => void;
  onCreate: (payload: TeamCreatePayload) => void;
  onUpdate: (teamId: string, payload: TeamUpdatePayload) => void;
}) {
  const dialogRef = useDialogDismiss(onClose, pending);
  const existing = state.mode === "edit" ? state.team : null;
  const [alias, setAlias] = useState(existing?.team_alias ?? "");
  const [teamId, setTeamId] = useState(existing?.team_id ?? "");
  const [models, setModels] = useState<ModelSelection>({
    models: existing?.models ?? [],
    all: !existing?.models?.length,
  });
  const [modelError, setModelError] = useState("");
  const [budget, setBudget] = useState(
    existing?.max_budget != null ? String(existing.max_budget) : "",
  );
  // A config-managed team's budget is its organization group's per-user limit.
  const perUserNode = existing?.organization_managed
    ? (existing.organization_node_id ?? null)
    : null;
  const configuredPerUser =
    existing?.organization_per_user != null
      ? String(existing.organization_per_user)
      : "";
  const [perUserLimit, setPerUserLimit] = useState(configuredPerUser);
  const [savingPerUser, setSavingPerUser] = useState(false);
  const [budgetDuration, setBudgetDuration] = useState(
    existing?.budget_duration ?? "",
  );
  const [tpm, setTpm] = useState(
    existing?.tpm_limit != null ? String(existing.tpm_limit) : "",
  );
  const [rpm, setRpm] = useState(
    existing?.rpm_limit != null ? String(existing.rpm_limit) : "",
  );
  const [blocked, setBlocked] = useState(existing?.blocked ?? false);
  const [windowChoices, setWindowChoices] = useState<
    Record<string, WindowChoice>
  >(() => (budgetWindows ? initialChoices(budgetWindows, existing) : {}));
  const windowBudgets = budgetWindows
    ? choicePayload(windowChoices, existing?.window_config)
    : undefined;
  const advanced = useRef<AdvancedPolicyHandle>(null);
  useEffect(() => {
    advanced.current?.setServerError(error);
  }, [error]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!models.all && !models.models.length) {
      setModelError("Select at least one model or allow all models.");
      return;
    }
    setModelError("");
    let advancedSettings: Record<string, unknown>;
    try {
      advancedSettings = advanced.current?.read() ?? {};
    } catch (failure) {
      setModelError((failure as Error).message);
      return;
    }
    const advancedPayload = Object.keys(advancedSettings).length
      ? { advanced_settings: advancedSettings }
      : {};
    const modelList = models.all ? [] : models.models;
    if (state.mode === "create") {
      const payload: TeamCreatePayload = {
        ...advancedPayload,
        team_alias: alias.trim(),
        models: modelList,
        blocked,
      };
      if (windowBudgets) payload.window_budgets = windowBudgets;
      if (teamId.trim()) payload.team_id = teamId.trim();
      const maxBudget = optionalNumber(budget);
      const tpmLimit = optionalNumber(tpm);
      const rpmLimit = optionalNumber(rpm);
      if (maxBudget !== undefined) payload.max_budget = maxBudget;
      if (!budgetWindows && budgetDuration.trim())
        payload.budget_duration = budgetDuration.trim();
      if (tpmLimit !== undefined) payload.tpm_limit = tpmLimit;
      if (rpmLimit !== undefined) payload.rpm_limit = rpmLimit;
      onCreate(payload);
      return;
    }
    if (perUserNode && perUserLimit.trim() !== configuredPerUser) {
      setSavingPerUser(true);
      try {
        await api.setGroupPerUser(perUserNode, perUserLimit.trim() || null);
      } catch (failure) {
        setModelError((failure as Error).message);
        return;
      } finally {
        setSavingPerUser(false);
      }
    }
    onUpdate(state.team.team_id, {
      ...advancedPayload,
      team_alias: alias.trim(),
      models: modelList,
      ...(!state.team.organization_managed
        ? {
            max_budget: nullableNumber(budget),
            // With budget windows on, the old reset period is not shown or sent.
            ...(!budgetWindows
              ? { budget_duration: budgetDuration.trim() || null }
              : {}),
          }
        : {}),
      ...(windowBudgets ? { window_budgets: windowBudgets } : {}),
      tpm_limit: nullableNumber(tpm),
      rpm_limit: nullableNumber(rpm),
      blocked,
    });
  }

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[2px]"
      role="dialog"
      ref={dialogRef}
      aria-modal="true"
      aria-labelledby="team-editor-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onClose();
      }}
    >
      <form
        onSubmit={(event) => void submit(event)}
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line-soft bg-card p-5 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3
              id="team-editor-title"
              className="text-lg font-semibold text-ink"
            >
              {state.mode === "create" ? "Create team" : "Edit team"}
            </h3>
            <p className="mt-1 text-xs text-ink-4">
              Choose allowed models below. Blank numeric limits remove the limit
              when editing.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close team editor"
            className="rounded p-1 text-ink-4 hover:bg-ink/[0.06] hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>
        {existing && (
          <section
            aria-label="Current team settings"
            className="mt-4 space-y-2 rounded-xl bg-well px-4 py-3"
          >
            <h4 className="text-sm font-semibold text-ink">
              Current team settings
            </h4>
            <CurrentPolicySettings
              settings={existing}
              hideReset={!!budgetWindows}
            />
          </section>
        )}
        <DurationChoices id="team-budget-durations" />
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="space-y-1 text-xs text-ink-3">
            <span>Team name</span>
            <input
              data-dialog-autofocus
              className={inputClass}
              value={alias}
              placeholder={existing?.team_alias || "Team name"}
              onChange={(event) => setAlias(event.target.value)}
              maxLength={128}
              required
            />
          </label>
          <label className="space-y-1 text-xs text-ink-3">
            <span>Team ID {state.mode === "create" && "(optional)"}</span>
            <input
              className={`${inputClass} font-mono`}
              value={teamId}
              onChange={(event) => setTeamId(event.target.value)}
              maxLength={128}
              disabled={state.mode === "edit"}
              placeholder={
                existing?.team_id ?? "Generated by LiteLLM when empty"
              }
            />
          </label>
          {perUserNode ? (
            <NumericPolicyInput
              label="Per-user limit (USD)"
              value={perUserLimit}
              onValueChange={setPerUserLimit}
              step="any"
              placeholder="Configured value"
            />
          ) : (
            <NumericPolicyInput
              label="Maximum budget (USD)"
              disabled={existing?.organization_managed}
              value={budget}
              onValueChange={setBudget}
              step="any"
              placeholder={
                existing
                  ? currentLimitPlaceholder(existing.max_budget)
                  : "Unlimited"
              }
            />
          )}
          {!budgetWindows && (
            <label className="space-y-1 text-xs text-ink-3">
              <span>Budget reset</span>
              <input
                disabled={existing?.organization_managed}
                className={inputClass}
                value={budgetDuration}
                list="team-budget-durations"
                onChange={(event) => setBudgetDuration(event.target.value)}
                placeholder={
                  existing
                    ? existing.budget_duration === undefined
                      ? "Not provided"
                      : existing.budget_duration || "No reset"
                    : "For example 30d"
                }
                maxLength={32}
              />
            </label>
          )}
          {budgetWindows && (
            <WindowBudgetFields
              schedule={budgetWindows}
              values={windowChoices}
              locked={existing?.window_config}
              onChange={(name, value) =>
                setWindowChoices((current) => ({ ...current, [name]: value }))
              }
            />
          )}
          {perUserNode && (
            <p className="text-xs text-ink-4 sm:col-span-2">
              The per-user limit caps each member's key in this organization
              group. Clear it to use the organization configuration again.
            </p>
          )}
          <NumericPolicyInput
            label="TPM limit"
            value={tpm}
            onValueChange={setTpm}
            placeholder={
              existing
                ? currentLimitPlaceholder(existing.tpm_limit)
                : "Unlimited"
            }
          />
          <NumericPolicyInput
            label="RPM limit"
            value={rpm}
            onValueChange={setRpm}
            placeholder={
              existing
                ? currentLimitPlaceholder(existing.rpm_limit)
                : "Unlimited"
            }
          />
          <ModelChoices
            value={models}
            onChange={setModels}
            knownModels={existing?.models ?? []}
          />
          <label className="flex items-center gap-2 text-sm text-ink-2 sm:col-span-2">
            <input
              type="checkbox"
              checked={blocked}
              onChange={(event) => setBlocked(event.target.checked)}
            />{" "}
            Block requests from this team
          </label>
          <AdvancedPolicySettings
            ref={advanced}
            operation={state.mode === "create" ? "team_create" : "team_update"}
            excludedFields={[
              "team_alias",
              "team_id",
              "models",
              "max_budget",
              "budget_duration",
              "tpm_limit",
              "rpm_limit",
              "blocked",
              ...(budgetWindows ? ["budget_limits"] : []),
            ]}
            current={
              existing
                ? { ...existing, ...existing.advanced_settings }
                : undefined
            }
          />
        </div>
        {(modelError || error) && (
          <p className="mt-4 rounded-lg border border-transparent bg-danger-tint px-3 py-2 text-xs text-danger">
            {modelError || error?.message}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-ink/[0.06] px-4 py-2 text-sm font-medium text-ink hover:bg-ink/10"
          >
            Cancel
          </button>
          <button
            disabled={
              pending || savingPerUser || operationsBlocked || !alias.trim()
            }
            className="rounded-lg bg-blue-solid px-4 py-2 text-sm font-semibold text-paper hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pending
              ? "Saving..."
              : operationsBlocked
                ? "Team actions paused"
                : state.mode === "create"
                  ? "Create team"
                  : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}

function DeleteTeamDialog({
  team,
  pending,
  operationsBlocked,
  error,
  onClose,
  onDelete,
}: {
  team: TeamInfo;
  pending: boolean;
  operationsBlocked: boolean;
  error?: string;
  onClose: () => void;
  onDelete: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const dialogRef = useDialogDismiss(onClose, pending);
  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[2px]"
      role="dialog"
      ref={dialogRef}
      aria-modal="true"
      aria-labelledby="delete-team-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-line-soft bg-card p-5 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-danger-tint p-2 text-danger">
            <ShieldAlert size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <h3 id="delete-team-title" className="font-semibold text-ink">
              Delete {team.team_alias || team.team_id}?
            </h3>
            <p className="mt-1 text-xs leading-5 text-ink-3">
              LiteLLM deletes this team and its team-scoped API keys. This
              cannot be undone by LiteGate.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close delete dialog"
            className="text-ink-4 hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>
        <label className="mt-4 block space-y-1 text-xs text-ink-3">
          <span>
            Type <code className="text-danger">{team.team_id}</code> to confirm
          </span>
          <input
            data-dialog-autofocus
            className={inputClass}
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </label>
        {error && <p className="mt-3 text-xs text-danger">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-line px-4 py-2 text-sm text-ink-2"
          >
            Cancel
          </button>
          <button
            onClick={onDelete}
            disabled={
              pending || operationsBlocked || confirmation !== team.team_id
            }
            className="rounded-lg bg-danger-solid px-4 py-2 text-sm font-semibold text-paper hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {pending
              ? "Deleting..."
              : operationsBlocked
                ? "Team actions paused"
                : "Delete team and keys"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminTeams({
  budgetWindows,
}: {
  budgetWindows?: BudgetWindowSchedule | null;
} = {}) {
  const queryClient = useQueryClient();
  const { operationsBlocked, retryAfter, refreshOperationLimit } =
    useOperationLimit();
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TeamInfo | null>(null);
  const [memberTeam, setMemberTeam] = useState<TeamInfo | null>(null);

  // The public schedule omits configured caps; administrators load them here.
  const adminWindows = useQuery({
    queryKey: ["budget-windows"],
    queryFn: api.budgetWindows,
    enabled: !!budgetWindows,
    staleTime: Infinity,
  });
  const schedule = budgetWindows ? (adminWindows.data ?? budgetWindows) : null;
  const teams = useQuery({
    queryKey: ["teams", page, search],
    queryFn: () => api.listTeams(page, 25, search),
    placeholderData: (previous) => previous,
  });
  const create = useMutation({
    mutationFn: api.createTeam,
    onSuccess: () => {
      setEditor(null);
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onSettled: refreshOperationLimit,
  });
  const update = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: TeamUpdatePayload }) =>
      api.updateTeam(id, payload),
    onSuccess: () => {
      setEditor(null);
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
    onSettled: refreshOperationLimit,
  });
  const remove = useMutation({
    mutationFn: api.deleteTeam,
    onSuccess: () => {
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
    onSettled: refreshOperationLimit,
  });
  const moveMember = useMutation({
    mutationFn: ({
      sourceTeamId,
      userId,
      destinationTeamId,
    }: {
      sourceTeamId: string;
      userId: string;
      destinationTeamId: string;
    }) =>
      api.moveTeamMember(sourceTeamId, {
        user_id: userId,
        destination_team_id: destinationTeamId,
        confirm_policy_change: true,
      }),
    onSuccess: () => {
      setMemberTeam(null);
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
    onSettled: refreshOperationLimit,
  });

  function applySearch(event: React.FormEvent) {
    event.preventDefault();
    setPage(1);
    setSearch(searchInput.trim());
  }
  function openCreate() {
    create.reset();
    update.reset();
    setEditor({ mode: "create" });
  }
  function openEdit(team: TeamInfo) {
    create.reset();
    update.reset();
    setEditor({ mode: "edit", team });
  }
  function openDelete(team: TeamInfo) {
    remove.reset();
    setDeleteTarget(team);
  }
  function openMembers(team: TeamInfo) {
    moveMember.reset();
    setMemberTeam(team);
  }

  const pageCount = Math.max(1, teams.data?.total_pages ?? 1);
  const pageError = teams.error as Error | null;
  const editorError = (
    editor?.mode === "create" ? create.error : update.error
  ) as Error | null;

  return (
    <section className="flex w-full flex-col gap-6">
      <PageHeader
        title="LiteLLM team policy"
        description="Manage team budgets, model access, rate limits, and availability without opening the LiteLLM admin UI."
        actions={
          <button
            type="button"
            onClick={openCreate}
            disabled={operationsBlocked}
            className={buttonCreate}
          >
            <Plus size={16} aria-hidden="true" />
            {operationsBlocked ? "Team actions paused" : "Create team"}
          </button>
        }
      />

      <Callout tone="warn" title="Deletion is intentionally guarded.">
        Deleting a LiteLLM team also deletes its team-scoped keys. Teams
        referenced by SSO mapping or <code>KEY_TEAM_ID</code> cannot be deleted
        until that configuration is changed.
      </Callout>
      {schedule && <BudgetWindowsBanner schedule={schedule} />}
      {operationsBlocked && (
        <DismissibleMessage
          messageKey="team-actions-paused"
          className="rounded-xl border border-transparent bg-orange-tint px-4 py-3 text-sm text-orange-ink"
        >
          Team actions are paused. Try again in {retryAfter || 1} seconds.
        </DismissibleMessage>
      )}
      {pageError && (
        <DismissibleMessage
          role="alert"
          messageKey={pageError.message}
          className="rounded-xl border border-transparent bg-danger-tint px-4 py-3 text-sm text-danger"
        >
          {pageError.message}
        </DismissibleMessage>
      )}

      <div className={`overflow-hidden ${card}`}>
        <div className={cardHeader}>
          <div className="flex items-center gap-3">
            <h2 className={cardTitle}>{teams.data?.total ?? 0} teams</h2>
            {teams.isFetching && (
              <span className="text-xs text-ink-4">Refreshing...</span>
            )}
          </div>
          <form
            onSubmit={applySearch}
            className="flex w-full gap-2 sm:w-auto sm:min-w-[360px]"
          >
            <div className="relative min-w-0 flex-1">
              <Search
                size={15}
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-4"
              />
              <input
                aria-label="Search teams"
                className={`${fieldInput} pl-9`}
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search team name or ID"
                maxLength={128}
              />
            </div>
            <button className={buttonSecondary}>Search</button>
          </form>
        </div>
        {teams.isLoading ? (
          <div className="h-48 animate-pulse bg-well" />
        ) : teams.data?.teams.length ? (
          <div className="relative overflow-x-auto">
            <div
              className={`${teamColumns} px-5 py-2.5 ${tableHead}`}
              aria-hidden="true"
            >
              <span>Team</span>
              <span>Spend / budget</span>
              <span>Models</span>
              <span>RPM / TPM</span>
              <span>Members / keys</span>
              <span className="text-right">Actions</span>
            </div>
            <div className="divide-y divide-line-soft">
              {teams.data.teams.map((team) => {
                const protectedTeam =
                  team.organization_managed ||
                  team.mapped_groups.length > 0 ||
                  team.default_key_team;
                const used =
                  team.max_budget && team.spend != null
                    ? (team.spend / team.max_budget) * 100
                    : null;
                return (
                  <article
                    key={team.team_id}
                    className={`${teamColumns} px-5 py-3.5 text-sm`}
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <span
                        aria-hidden="true"
                        className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-well text-ink-3"
                      >
                        <Building2 size={16} />
                      </span>
                      <div className="min-w-0">
                        <h3 className="truncate font-semibold text-ink">
                          {team.team_alias || "Unnamed team"}
                        </h3>
                        <p
                          className="truncate font-mono text-xs text-ink-4"
                          title={team.team_id}
                        >
                          {team.team_id}
                        </p>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {team.blocked && <Pill tone="bad">Blocked</Pill>}
                          {team.organization_managed && (
                            <span
                              title="Managed by the organization hierarchy configuration, including Helm values"
                              className="rounded-md bg-blue-tint px-2 py-0.5 text-xs font-semibold text-blue-ink"
                            >
                              Config managed
                            </span>
                          )}
                          {team.default_key_team && (
                            <span className="rounded-md bg-blue-tint px-2 py-0.5 text-xs font-semibold text-blue-ink">
                              Default key team
                            </span>
                          )}
                          {team.mapped_groups.map((group) => (
                            <span
                              key={group}
                              className="rounded-md bg-well px-2 py-0.5 text-xs font-medium text-ink-3"
                            >
                              SSO: {group}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <p className="text-[13px]">
                        <span className="sr-only">Spend: </span>
                        <span className="font-semibold text-ink">
                          {metricValue(team.spend ?? 0, "spend")}
                        </span>{" "}
                        <span className="text-ink-4">
                          {team.max_budget != null
                            ? `of ${metricValue(team.max_budget, "spend")}`
                            : "· Unlimited"}
                        </span>
                      </p>
                      {used != null && <UsageBar percent={used} />}
                      {!budgetWindows && team.budget_duration && (
                        <p className="text-xs text-ink-4">
                          {resetLabel(team.budget_duration)}
                        </p>
                      )}
                      {budgetWindows && (
                        <TeamWindowUsage teamId={team.team_id} />
                      )}
                    </div>
                    <p className="text-[13px] text-ink-2">
                      <span className="sr-only">Models: </span>
                      {team.models?.length
                        ? `${team.models.length} ${team.models.length === 1 ? "model" : "models"}`
                        : "All"}
                    </p>
                    <p className="text-[13px] text-ink-2">
                      <span className="sr-only">
                        Requests per minute / tokens per minute:{" "}
                      </span>
                      {team.rpm_limit?.toLocaleString() ?? "Default"}
                      <span className="text-ink-4"> / </span>
                      {team.tpm_limit?.toLocaleString() ?? "Default"}
                    </p>
                    <p className="text-[13px] text-ink-2">
                      <span className="sr-only">Members / keys: </span>
                      {team.members_count ?? 0} / {team.keys_count ?? 0}
                    </p>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => openMembers(team)}
                        disabled={operationsBlocked}
                        className={buttonSmall}
                      >
                        <Users size={13} aria-hidden="true" /> Members
                      </button>
                      <button
                        type="button"
                        onClick={() => openEdit(team)}
                        disabled={operationsBlocked}
                        className={buttonSmall}
                      >
                        <Edit3 size={13} aria-hidden="true" /> Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => openDelete(team)}
                        disabled={protectedTeam || operationsBlocked}
                        title={
                          protectedTeam
                            ? "Remove SSO/default-team configuration references first"
                            : operationsBlocked
                              ? "Wait for the operation cooldown"
                              : "Delete team"
                        }
                        className={buttonSmallDanger}
                      >
                        <Trash2 size={13} aria-hidden="true" /> Delete
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        ) : (
          <p className="p-10 text-center text-sm text-ink-4">
            {search
              ? "No teams match this search."
              : "No LiteLLM teams yet. Create the first team to define a shared budget and model policy."}
          </p>
        )}
        <div className="flex items-center justify-between border-t border-line-soft px-5 py-3 text-[13px]">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page <= 1}
            className={buttonSmall}
          >
            Previous
          </button>
          <span className="text-ink-4">
            Page {page} of {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
            disabled={page >= pageCount}
            className={buttonSmall}
          >
            Next
          </button>
        </div>
      </div>

      {editor && (
        <TeamEditor
          key={editor.mode === "edit" ? editor.team.team_id : "create"}
          state={editor}
          pending={create.isPending || update.isPending}
          operationsBlocked={operationsBlocked}
          error={editorError}
          onClose={() => setEditor(null)}
          onCreate={(payload) => create.mutate(payload)}
          onUpdate={(id, payload) => update.mutate({ id, payload })}
          budgetWindows={schedule}
        />
      )}
      {deleteTarget && (
        <DeleteTeamDialog
          team={deleteTarget}
          pending={remove.isPending}
          operationsBlocked={operationsBlocked}
          error={(remove.error as Error | null)?.message}
          onClose={() => setDeleteTarget(null)}
          onDelete={() => remove.mutate(deleteTarget.team_id)}
        />
      )}
      {memberTeam && (
        <TeamMembersDialog
          team={memberTeam}
          pending={moveMember.isPending}
          operationsBlocked={operationsBlocked}
          error={(moveMember.error as Error | null)?.message}
          onClose={() => setMemberTeam(null)}
          onMove={(userId, destinationTeamId) =>
            moveMember.mutate({
              sourceTeamId: memberTeam.team_id,
              userId,
              destinationTeamId,
            })
          }
        />
      )}
    </section>
  );
}
