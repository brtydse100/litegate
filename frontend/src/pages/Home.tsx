import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, useLocation } from "react-router-dom";
import {
  Activity,
  BookOpen,
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  Gauge,
  KeyRound,
  LogOut,
  RefreshCw,
  Shield,
  Ticket,
  Users,
  Zap,
} from "lucide-react";
import AdminKeys from "../components/AdminKeys";
import AdminStatus from "../components/AdminStatus";
import AdminUsers from "../components/AdminUsers";
import AdminTeams from "../components/AdminTeams";
import ThemeToggle from "../components/ThemeToggle";
import { api } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { useOperationLimit } from "../hooks/useOperationLimit";
import type { KeyInfo } from "../types";

interface PortalConfig {
  support_ticket_url: string;
  logo_url: string;
  litellm_ui_url: string;
  api_docs_url: string;
  local_users_enabled: boolean;
}

const primaryKeyActionClassName =
  "flex min-h-16 w-full items-center justify-center gap-3 rounded-lg bg-indigo-600 px-8 py-5 text-lg font-semibold text-white shadow-lg shadow-indigo-200/60 transition-colors hover:bg-indigo-700 disabled:opacity-50 [html.dark_&]:shadow-indigo-950/50";

async function fetchPortalConfig(): Promise<PortalConfig> {
  const response = await fetch("/api/portal-config");
  if (!response.ok) throw new Error("Could not load portal configuration");
  return response.json();
}

function Brand({ logoUrl }: { logoUrl?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      {logoUrl ? (
        <img
          src={logoUrl}
          alt="LiteGate"
          className="h-7 w-auto object-contain"
        />
      ) : (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-indigo-600 text-white shadow-sm">
          <Zap size={14} fill="currentColor" />
        </div>
      )}
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold tracking-tight text-slate-950">
          LiteGate
        </p>
        <p className="truncate text-[10px] text-slate-500">
          LiteLLM access portal
        </p>
      </div>
    </div>
  );
}

function KeyCard({ keyInfo }: { keyInfo: KeyInfo }) {
  const [copied, setCopied] = useState(false);
  const token = keyInfo.token ?? "";
  const display = token
    ? `${token.slice(0, 9)}${"•".repeat(8)}${token.slice(-4)}`
    : "Hidden — regenerate to reveal";

  async function copy() {
    if (!token) return;
    await navigator.clipboard.writeText(token);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <article className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="rounded-md border border-indigo-100 bg-indigo-50 p-2 text-indigo-600">
            <KeyRound size={17} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-950">
              {keyInfo.key_alias || "API key"}
            </p>
            <p className="text-xs text-slate-500">Virtual key</p>
          </div>
        </div>
        <div className="flex min-w-0 items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
          <code className="min-w-0 flex-1 truncate font-mono text-xs text-slate-700">
            {display}
          </code>
          {token && (
            <button
              onClick={copy}
              title="Copy key identifier"
              className="text-slate-400 hover:text-slate-900"
            >
              {copied ? (
                <Check size={15} className="text-emerald-600" />
              ) : (
                <Copy size={15} />
              )}
            </button>
          )}
        </div>
      </div>
      <dl className="grid divide-y divide-slate-200 text-sm sm:grid-cols-4 sm:divide-x sm:divide-y-0">
        <div className="px-5 py-4">
          <dt className="text-xs text-slate-500">Spend</dt>
          <dd className="mt-1 font-semibold text-slate-950">
            ${keyInfo.spend.toFixed(4)}
          </dd>
        </div>
        <div className="px-5 py-4">
          <dt className="text-xs text-slate-500">Budget</dt>
          <dd className="mt-1 font-semibold text-slate-950">
            {keyInfo.max_budget != null
              ? `$${keyInfo.max_budget}`
              : "Unlimited"}
          </dd>
        </div>
        <div className="px-5 py-4">
          <dt className="text-xs text-slate-500">Models</dt>
          <dd className="mt-1 font-semibold text-slate-950">
            {keyInfo.models?.length ? keyInfo.models.length : "All"}
          </dd>
        </div>
        <div className="px-5 py-4">
          <dt className="text-xs text-slate-500">Expires</dt>
          <dd className="mt-1 font-semibold text-slate-950">
            {keyInfo.expires
              ? new Date(keyInfo.expires).toLocaleDateString()
              : "Never"}
          </dd>
        </div>
      </dl>
      {keyInfo.team_id && (
        <div className="flex items-center gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3 text-xs text-slate-600">
          <Building2 size={13} />
          Assigned through{" "}
          <span className="font-medium text-slate-800">{keyInfo.team_id}</span>
        </div>
      )}
    </article>
  );
}

export function AccessSnapshot({ keys }: { keys: KeyInfo[] }) {
  const [modelsExpanded, setModelsExpanded] = useState(false);
  const first = keys[0];
  const hasUnrestrictedModelAccess = keys.some(
    (keyInfo) => !keyInfo.models?.length,
  );
  const accessibleModels = Array.from(
    new Set(keys.flatMap((keyInfo) => keyInfo.models ?? [])),
  ).sort((left, right) => left.localeCompare(right));
  const items = [
    {
      label: "Gateway status",
      value: "Ready",
      icon: Check,
      tone: "text-emerald-600 bg-emerald-50",
    },
    {
      label: "Model access",
      value: hasUnrestrictedModelAccess
        ? "All models"
        : accessibleModels.length
          ? `${accessibleModels.length} models`
          : "All models",
      icon: Zap,
      tone: "text-indigo-600 bg-indigo-50",
    },
    {
      label: "Rate limit",
      value:
        first?.rpm_limit != null
          ? `${first.rpm_limit.toLocaleString()} RPM`
          : "Default limits",
      icon: Gauge,
      tone: "text-amber-600 bg-amber-50",
    },
  ];
  return (
    <section className="space-y-3" aria-label="Access snapshot">
      <div className="grid gap-3 sm:grid-cols-3">
        {items.map((item) => {
          const content = (
            <>
              <span className={`rounded-md p-2 ${item.tone}`}>
                <item.icon size={16} />
              </span>
              <div className="min-w-0 flex-1 text-left">
                <p className="text-xs text-slate-500">{item.label}</p>
                <p className="mt-0.5 text-sm font-semibold text-slate-950">
                  {item.value}
                </p>
              </div>
            </>
          );

          return item.label === "Model access" ? (
            <button
              key={item.label}
              type="button"
              onClick={() => setModelsExpanded((expanded) => !expanded)}
              aria-expanded={modelsExpanded}
              aria-controls="accessible-models"
              className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-indigo-200 hover:bg-indigo-50/30"
            >
              {content}
              <ChevronDown
                size={16}
                className={`text-slate-400 transition-transform ${modelsExpanded ? "rotate-180" : ""}`}
              />
            </button>
          ) : (
            <div
              key={item.label}
              className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
            >
              {content}
            </div>
          );
        })}
      </div>
      {modelsExpanded && (
        <div
          id="accessible-models"
          className="rounded-lg border border-indigo-100 bg-white p-5 shadow-sm"
        >
          <h2 className="text-sm font-semibold text-slate-950">
            Accessible models
          </h2>
          {hasUnrestrictedModelAccess ? (
            <p className="mt-2 text-sm text-slate-600">
              Your key can access all models available through this LiteLLM
              gateway.
            </p>
          ) : (
            <ul className="mt-3 flex flex-wrap gap-2">
              {accessibleModels.map((model) => (
                <li
                  key={model}
                  className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 font-mono text-xs text-slate-700"
                >
                  {model}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

export default function Home() {
  const { user, login, logout } = useAuth();
  const queryClient = useQueryClient();
  const location = useLocation();
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const [demoRolePending, setDemoRolePending] = useState(false);

  const portal = useQuery({
    queryKey: ["portal-config"],
    queryFn: fetchPortalConfig,
    staleTime: Infinity,
  });
  const keys = useQuery({ queryKey: ["keys"], queryFn: api.listKeys });
  const { operationsBlocked, retryAfter, refreshOperationLimit } =
    useOperationLimit();
  const keyList = keys.data?.keys ?? [];
  const hasKey = keyList.length > 0;

  const create = useMutation({
    mutationFn: api.createKey,
    onSuccess: (result) => {
      setNewKey(result.key);
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
    onSettled: refreshOperationLimit,
  });
  const regenerate = useMutation({
    mutationFn: api.regenerateKey,
    onSuccess: (result) => {
      setNewKey(result.key);
      setConfirmRegenerate(false);
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
    onSettled: refreshOperationLimit,
  });
  const mutationError = create.error ?? regenerate.error ?? keys.error;

  async function copyNewKey() {
    if (!newKey) return;
    await navigator.clipboard.writeText(newKey);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  async function switchDemoRole(role: "admin" | "user") {
    if (import.meta.env.VITE_DEMO_MODE !== "true" || user?.role === role)
      return;
    setDemoRolePending(true);
    try {
      const response = await fetch("/api/demo/role", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      if (!response.ok) throw new Error("Could not switch the demo role");
      await login();
    } finally {
      setDemoRolePending(false);
    }
  }

  const config = portal.data;
  const isAdmin = user?.role === "admin";
  const localUsersEnabled = config?.local_users_enabled ?? true;
  const section = location.pathname === "/" ? "/my-key" : location.pathname;
  const adminSections = new Set([
    "/keys",
    ...(localUsersEnabled ? ["/users"] : []),
    "/teams",
    "/status",
  ]);
  if (location.pathname === "/") return <Navigate to="/my-key" replace />;
  if (
    (!isAdmin && section !== "/my-key") ||
    (isAdmin && section !== "/my-key" && !adminSections.has(section))
  ) {
    return <Navigate to="/my-key" replace />;
  }

  const titles: Record<string, string> = {
    "/my-key": "My API access",
    "/keys": "Key policies",
    "/users": "Local users",
    "/teams": "Teams",
    "/status": "System status",
  };
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
      isActive
        ? "bg-slate-100 font-medium text-slate-950"
        : "text-slate-600 hover:bg-slate-50 hover:text-slate-950"
    }`;
  const navItems = [
    { to: "/my-key", label: "My key", icon: KeyRound },
    ...(isAdmin
      ? [
          { to: "/keys", label: "Key policies", icon: Shield },
          ...(localUsersEnabled
            ? [{ to: "/users", label: "Local users", icon: Users }]
            : []),
          { to: "/teams", label: "Teams", icon: Building2 },
          { to: "/status", label: "Status", icon: Activity },
        ]
      : []),
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 md:flex md:h-screen md:overflow-hidden">
      <aside className="hidden w-60 flex-none flex-col border-r border-slate-200 bg-white md:flex">
        <div className="flex h-14 items-center border-b border-slate-200 px-4">
          <Brand logoUrl={config?.logo_url} />
        </div>
        <nav
          className="flex-1 space-y-5 overflow-y-auto px-3 py-4"
          aria-label="Primary navigation"
        >
          <div>
            <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Workspace
            </p>
            <NavLink to="/my-key" className={navClass}>
              <KeyRound size={16} /> My key
            </NavLink>
          </div>
          {isAdmin && (
            <>
              <div>
                <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Access control
                </p>
                <div className="space-y-0.5">
                  <NavLink to="/keys" className={navClass}>
                    <Shield size={16} /> Key policies
                  </NavLink>
                  {localUsersEnabled && (
                    <NavLink to="/users" className={navClass}>
                      <Users size={16} /> Local users
                    </NavLink>
                  )}
                  <NavLink to="/teams" className={navClass}>
                    <Building2 size={16} /> Teams
                  </NavLink>
                </div>
              </div>
              <div>
                <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Operations
                </p>
                <NavLink to="/status" className={navClass}>
                  <Activity size={16} /> Status
                </NavLink>
              </div>
            </>
          )}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <div className="flex items-center gap-2.5 rounded-md px-2 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-50 text-xs font-semibold text-indigo-700">
              {user?.email?.slice(0, 2).toUpperCase() || "LG"}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-slate-800">
                {user?.email}
              </p>
              <p className="text-[10px] capitalize text-slate-500">
                {user?.role || "user"}
              </p>
            </div>
            <button
              onClick={() => void logout()}
              aria-label="Sign out"
              title="Sign out"
              className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-800"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1 md:flex md:flex-col md:overflow-hidden">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white md:static md:flex-none">
          <div className="flex h-14 items-center justify-between gap-4 px-4 sm:px-6">
            <div className="md:hidden">
              <Brand logoUrl={config?.logo_url} />
            </div>
            <div className="hidden min-w-0 items-center gap-2 text-sm md:flex">
              <span className="text-slate-400">LiteGate</span>
              <ChevronRight size={14} className="text-slate-300" />
              <span className="truncate font-medium text-slate-700">
                {titles[section]}
              </span>
            </div>
            <div className="flex items-center gap-1">
              {import.meta.env.VITE_DEMO_MODE === "true" && (
                <div
                  className="mr-1 flex items-center rounded-md border border-slate-200 bg-slate-50 p-0.5"
                  aria-label="Demo role"
                >
                  {(["user", "admin"] as const).map((role) => (
                    <button
                      key={role}
                      type="button"
                      onClick={() => void switchDemoRole(role)}
                      disabled={demoRolePending}
                      aria-label={`View demo as ${role}`}
                      className={`rounded px-2.5 py-1 text-[11px] font-medium capitalize transition-colors disabled:opacity-50 ${
                        user?.role === role
                          ? "bg-white text-slate-900 shadow-sm"
                          : "text-slate-500 hover:text-slate-900"
                      }`}
                    >
                      {role}
                    </button>
                  ))}
                </div>
              )}
              {config?.api_docs_url && (
                <a
                  href={config.api_docs_url}
                  target="_blank"
                  rel="noreferrer"
                  className="hidden items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-900 sm:flex"
                >
                  <BookOpen size={14} /> Docs
                </a>
              )}
              <ThemeToggle />
              <button
                onClick={() => void logout()}
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-900 md:hidden"
              >
                <LogOut size={14} />{" "}
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </div>
          </div>
          <nav
            className="flex gap-1 overflow-x-auto border-t border-slate-100 px-3 py-2 md:hidden"
            aria-label="Mobile navigation"
          >
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={navClass}>
                <item.icon size={15} /> {item.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-7 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-6xl">
            {section === "/users" && isAdmin ? (
              <AdminUsers />
            ) : section === "/teams" && isAdmin ? (
              <AdminTeams />
            ) : section === "/keys" && isAdmin ? (
              <AdminKeys />
            ) : section === "/status" && isAdmin ? (
              <AdminStatus />
            ) : (
              <section className="w-full space-y-6">
                <div>
                  <p className="text-xs font-medium text-indigo-600">
                    Virtual keys
                  </p>
                  <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
                    Your API access
                  </h1>
                  <p className="mt-1 max-w-2xl text-sm text-slate-500">
                    Create and manage your governed LiteLLM key. Secrets are
                    only shown once when created or regenerated.
                  </p>
                </div>

                {mutationError && (
                  <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {(mutationError as Error).message}
                  </p>
                )}
                {operationsBlocked && (
                  <p className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    Key actions are paused. Try again in {retryAfter || 1}{" "}
                    seconds.
                  </p>
                )}
                {newKey && (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-5">
                    <p className="text-sm font-medium text-emerald-900">
                      Copy this key now — it will not be shown in full again.
                    </p>
                    <div className="mt-3 flex max-w-2xl gap-2">
                      <code className="min-w-0 flex-1 truncate rounded-md border border-emerald-200 bg-white px-3 py-2 text-sm text-emerald-800">
                        {newKey}
                      </code>
                      <button
                        onClick={copyNewKey}
                        className="rounded-md border border-emerald-200 bg-white px-3 text-emerald-700 hover:bg-emerald-100"
                      >
                        {copied ? <Check size={15} /> : <Copy size={15} />}
                      </button>
                    </div>
                    <button
                      onClick={() => setNewKey(null)}
                      className="mt-3 text-xs font-medium text-emerald-700 hover:text-emerald-900"
                    >
                      Dismiss
                    </button>
                  </div>
                )}
                {confirmRegenerate && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-5">
                    <p className="text-sm font-semibold text-amber-950">
                      Replace the current key?
                    </p>
                    <p className="mt-1 text-sm text-amber-800">
                      The old key stops working immediately.
                    </p>
                    <div className="mt-4 flex gap-2">
                      <button
                        onClick={() => regenerate.mutate()}
                        disabled={regenerate.isPending || operationsBlocked}
                        className="rounded-md bg-amber-600 px-4 py-2 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                      >
                        {regenerate.isPending
                          ? "Replacing..."
                          : operationsBlocked
                            ? "Temporarily paused"
                            : "Replace key"}
                      </button>
                      <button
                        onClick={() => setConfirmRegenerate(false)}
                        className="rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                {keys.isLoading ? (
                  <div className="h-44 animate-pulse rounded-lg border border-slate-200 bg-white" />
                ) : (
                  keyList.map((keyInfo, index) => (
                    <KeyCard key={keyInfo.token ?? index} keyInfo={keyInfo} />
                  ))
                )}
                {!keys.isLoading && !confirmRegenerate && (
                  <div className="w-full">
                    {!hasKey ? (
                      <button
                        onClick={() => create.mutate()}
                        disabled={create.isPending || operationsBlocked}
                        className={primaryKeyActionClassName}
                      >
                        <Zap size={21} />{" "}
                        {create.isPending
                          ? "Creating..."
                          : operationsBlocked
                            ? "Key actions paused"
                            : "Create API key"}
                      </button>
                    ) : (
                      <button
                        onClick={() => setConfirmRegenerate(true)}
                        disabled={operationsBlocked}
                        className={primaryKeyActionClassName}
                      >
                        <RefreshCw size={21} />{" "}
                        {operationsBlocked
                          ? "Regeneration paused"
                          : "Regenerate key"}
                      </button>
                    )}
                  </div>
                )}
                {hasKey && <AccessSnapshot keys={keyList} />}
                {(config?.litellm_ui_url || config?.support_ticket_url) && (
                  <div className="grid w-full gap-3 border-t border-slate-200 pt-5">
                    {config.litellm_ui_url && (
                      <a
                        href={config.litellm_ui_url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex min-h-14 w-full items-center justify-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-6 py-4 text-base font-semibold text-indigo-600 hover:bg-indigo-100 hover:text-indigo-800"
                      >
                        <ExternalLink size={15} /> Open LiteLLM model hub
                      </a>
                    )}
                    {config.support_ticket_url && (
                      <a
                        href={config.support_ticket_url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex min-h-16 w-full items-center justify-center gap-3 rounded-lg border-2 border-slate-300 bg-white px-8 py-5 text-lg font-semibold text-slate-800 shadow-sm transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                      >
                        <Ticket size={21} /> Support
                      </a>
                    )}
                  </div>
                )}
              </section>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
