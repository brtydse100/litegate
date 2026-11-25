import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useLocation } from "react-router-dom";
import {
  Activity,
  Clock3,
  KeyRound,
  LayoutGrid,
  List,
  User as UserIcon,
  Users,
} from "lucide-react";
import DismissibleMessage from "../components/DismissibleMessage";
import PersonalKeySecret from "../components/PersonalKeySecret";
import { keyToken } from "../components/BulkKeyEditor";
import { LoadingBlock, LoadingPage } from "../components/LoadingBlock";
import type { BudgetWindowSchedule } from "../types";

// Each page loads its code on first visit, so My key does not wait for admin pages.
const AdminKeys = lazy(() => import("../components/AdminKeys"));
const AdminAudit = lazy(() => import("../components/AdminAudit"));
const AdminStatus = lazy(() => import("../components/AdminStatus"));
const AdminUsers = lazy(() => import("../components/AdminUsers"));
const AdminTeams = lazy(() => import("../components/AdminTeams"));
const PersonalAnalytics = lazy(() => import("../components/PersonalAnalytics"));
const AdminOrganization = lazy(() => import("../components/AdminOrganization"));
import {
  AdminSidebar,
  BrandMark,
  DemoRoleSwitch,
  type DemoRole,
  UserMenu,
  type NavGroup,
} from "../components/AppChrome";
import { api } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { useFavicon } from "../hooks/useFavicon";
import { useOperationLimit } from "../hooks/useOperationLimit";
import {
  BudgetCard,
  CreateKeyCard,
  DetailsCard,
  KeyCard,
  LinkCard,
  RegenerateButton,
  RegenerateConfirm,
  StatusCard,
  keyAccessStatus,
} from "./MyKey";

interface PortalConfig {
  support_ticket_url: string;
  logo_url: string;
  my_key_text?: string;
  litellm_ui_url: string;
  api_docs_url: string;
  setup_guide_url?: string;
  local_users_enabled: boolean;
  save_api_keys_in_db: boolean;
  analytics_enabled?: boolean;
  organization_delegation_enabled?: boolean;
  hierarchical_budgets_enabled?: boolean;
  litellm_enterprise_enabled: boolean;
  team_budget_windows?: BudgetWindowSchedule | null;
}

async function fetchPortalConfig(): Promise<PortalConfig> {
  const response = await fetch("/api/portal-config");
  if (!response.ok) throw new Error("Could not load portal configuration");
  return response.json();
}

// The demo's team-owner choice outlives Home re-mounting after a sign-in
// refresh; a full reload resets the demo account and this together.
let rememberedDemoOwner: DemoRole | null = null;

export default function Home() {
  const { user, login, logout } = useAuth();
  const queryClient = useQueryClient();
  const location = useLocation();
  const [newKey, setNewKey] = useState<string | null>(null);
  const [previousKeyIds, setPreviousKeyIds] = useState<string[]>([]);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const [demoRolePending, setDemoRolePending] = useState(false);
  const [demoOwner, setDemoOwner] = useState<DemoRole | null>(
    () => rememberedDemoOwner,
  );

  function showKey(secret: string) {
    setPreviousKeyIds(keyList.map(keyToken));
    setNewKey(secret);
  }

  const portal = useQuery({
    queryKey: ["portal-config"],
    queryFn: fetchPortalConfig,
    staleTime: Infinity,
  });
  useFavicon(portal.data?.logo_url);
  const keys = useQuery({ queryKey: ["keys"], queryFn: api.listKeys });
  const { operationsBlocked, retryAfter, refreshOperationLimit } =
    useOperationLimit();
  const keyList = keys.data?.keys ?? [];
  const hasKey = keyList.length > 0;
  const newKeyIdentifier =
    newKey &&
    keyList.length === 1 &&
    !previousKeyIds.includes(keyToken(keyList[0]))
      ? keyToken(keyList[0])
      : null;

  const create = useMutation({
    mutationFn: api.createKey,
    onSuccess: (result) => {
      showKey(result.key);
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
    onSettled: refreshOperationLimit,
  });
  const regenerate = useMutation({
    mutationFn: api.regenerateKey,
    onSuccess: (result) => {
      showKey(result.key);
      setConfirmRegenerate(false);
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
    onSettled: refreshOperationLimit,
  });
  const mutationError = create.error ?? regenerate.error ?? keys.error;

  async function switchDemoRole(role: DemoRole) {
    if (import.meta.env.VITE_DEMO_MODE !== "true") return;
    setDemoRolePending(true);
    try {
      const response = await fetch("/api/demo/role", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      if (!response.ok) throw new Error("Could not switch the demo role");
      rememberedDemoOwner = role.endsWith("-owner") ? role : null;
      setDemoOwner(rememberedDemoOwner);
      // Organization data depends on who is looking; fetch it again.
      queryClient.removeQueries({
        predicate: (query) =>
          String(query.queryKey[0]).startsWith("organization"),
      });
      await login();
    } finally {
      setDemoRolePending(false);
    }
  }

  const config = portal.data;
  const isAdmin = user?.role === "admin";
  const organizationAccess = useQuery({
    queryKey: ["organization-access"],
    queryFn: () => api.organizationAccess(),
    enabled: !isAdmin && !!config?.organization_delegation_enabled,
    refetchInterval: 60_000,
    retry: false,
  });
  const systemStatus = useQuery({
    queryKey: ["system-status"],
    queryFn: api.getSystemStatus,
    enabled: isAdmin,
    refetchInterval: 30_000,
  });
  const canViewOrganization =
    isAdmin || organizationAccess.data?.organization === true;
  const analyticsEnabled = config?.analytics_enabled === true;
  const localUsersEnabled = config?.local_users_enabled ?? true;
  const section = location.pathname === "/" ? "/my-key" : location.pathname;
  if (
    (section === "/analytics" || section === "/organization") &&
    portal.isPending
  )
    return <LoadingPage label="Loading access…" />;
  if (
    section === "/organization" &&
    !isAdmin &&
    config?.organization_delegation_enabled &&
    organizationAccess.isPending
  )
    return <LoadingPage label="Checking organization access…" />;
  // Team owners get the sidebar layout; wait for their access instead of
  // flashing the ordinary top bar first.
  if (
    !isAdmin &&
    config?.organization_delegation_enabled &&
    organizationAccess.isPending
  )
    return <LoadingPage label="Loading access…" />;
  const adminSections = new Set([
    "/keys",
    "/users",
    "/teams",
    "/organization",
    "/status",
    "/audit",
    ...(analyticsEnabled ? ["/analytics"] : []),
  ]);
  if (location.pathname === "/") return <Navigate to="/my-key" replace />;
  if (
    (!isAdmin &&
      section !== "/my-key" &&
      !(section === "/analytics" && analyticsEnabled) &&
      !(section === "/organization" && canViewOrganization)) ||
    (isAdmin && section !== "/my-key" && !adminSections.has(section))
  ) {
    return <Navigate to="/my-key" replace />;
  }

  const signOut = () => void logout();
  const demoSwitch = (
    <DemoRoleSwitch
      role={demoOwner ?? (user?.role === "admin" ? "admin" : "user")}
      pending={demoRolePending}
      onSwitch={(role) => void switchDemoRole(role)}
    />
  );
  const adminHome = isAdmin || canViewOrganization ? "/organization" : null;
  // Delegated organization access is shown as its own role.
  const roleLabel = !isAdmin && canViewOrganization ? "Team owner" : user?.role;
  // Anyone with admin access keeps the sidebar, including on My key and
  // Analytics (listed under Workspace); ordinary users get the top bar.
  const adminLayout =
    !!adminHome || (section !== "/my-key" && section !== "/analytics");

  const notices = (
    <>
      {portal.isPending && (
        <p role="status" className="text-sm text-ink-4">
          Loading portal configuration…
        </p>
      )}
      {portal.isError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-transparent bg-danger-tint px-4 py-3 text-sm text-ink-2"
        >
          Portal configuration is unavailable. Retry before creating or
          replacing a key.
          <button
            type="button"
            disabled={portal.isFetching}
            onClick={() => {
              void portal.refetch();
            }}
            className="font-semibold text-blue-ink disabled:opacity-50"
          >
            Retry portal configuration
          </button>
        </div>
      )}
      {mutationError && (
        <DismissibleMessage
          role="alert"
          messageKey={(mutationError as Error).message}
          className="rounded-xl border border-transparent bg-danger-tint px-4 py-3 text-sm text-danger"
        >
          {(mutationError as Error).message}
        </DismissibleMessage>
      )}
      {keys.isError && (
        <button
          type="button"
          disabled={keys.isFetching}
          onClick={() => {
            void keys.refetch();
          }}
          className="self-start text-sm font-semibold text-blue-ink disabled:opacity-50"
        >
          Retry key information
        </button>
      )}
      {operationsBlocked && (
        <DismissibleMessage
          messageKey="key-actions-paused"
          className="rounded-xl border border-transparent bg-orange-tint px-4 py-3 text-sm text-orange-ink"
        >
          Key actions are paused. Try again in {retryAfter || 1} seconds.
        </DismissibleMessage>
      )}
      {newKey && !newKeyIdentifier && (
        <section
          aria-label="New key"
          className="flex flex-col gap-3 rounded-2xl border border-line-soft bg-card p-6"
        >
          <p className="text-sm font-semibold text-green-ink">
            Your API key is ready. Copy it before leaving this page.
          </p>
          <PersonalKeySecret
            identifier=""
            canReveal={false}
            initialSecret={newKey}
            onHide={() => setNewKey(null)}
          />
        </section>
      )}
    </>
  );

  // In stored-key mode, Show replaces regeneration (docs/features.md).
  const storedKeyMode =
    !!config?.save_api_keys_in_db &&
    keyList.some((key) => key.secret_available);
  const keyActionsReady =
    !portal.isPending && !portal.isError && !keys.isPending && !keys.isError;
  const regenerateAction =
    !keyActionsReady || newKey || storedKeyMode ? null : confirmRegenerate ? (
      <RegenerateConfirm
        pending={regenerate.isPending}
        paused={operationsBlocked}
        onConfirm={() => regenerate.mutate()}
        onCancel={() => setConfirmRegenerate(false)}
      />
    ) : (
      <RegenerateButton
        paused={operationsBlocked}
        onClick={() => setConfirmRegenerate(true)}
      />
    );
  const statusLabel = keys.isPending
    ? "Loading"
    : keys.isError && !hasKey
      ? "Status unavailable"
      : !hasKey
        ? "No key"
        : keyList.map(keyAccessStatus).includes("Ready")
          ? "Ready"
          : keyAccessStatus(keyList[0]);
  const helpfulLinks = [
    ...(config?.litellm_ui_url
      ? [{ href: config.litellm_ui_url, label: "Open LiteLLM model hub" }]
      : []),
    ...(config?.support_ticket_url
      ? [{ href: config.support_ticket_url, label: "Support" }]
      : []),
  ];

  const myKey = (
    <div className="flex flex-wrap items-start gap-6">
      <div className="flex min-w-0 flex-[999_1_520px] flex-col gap-5">
        <h1 className="sr-only">My key</h1>
        {notices}
        {keys.isLoading ? (
          <div
            role="status"
            className="h-80 animate-pulse rounded-2xl border border-line-soft bg-card"
          >
            <span className="sr-only">Loading key information…</span>
          </div>
        ) : !hasKey ? (
          keyActionsReady && !newKey ? (
            <CreateKeyCard
              pending={create.isPending}
              paused={operationsBlocked}
              savedKeys={!!config?.save_api_keys_in_db}
              onCreate={() => create.mutate()}
            />
          ) : (
            (keys.isPending || keys.isError) && (
              <p className="text-sm text-ink-4">
                {keys.isError
                  ? "Key information is unavailable. Retry before creating or replacing a key."
                  : "Loading key information…"}
              </p>
            )
          )
        ) : (
          keyList.map((keyInfo, index) => (
            <div key={keyInfo.token ?? index} className="flex flex-col gap-5">
              <BudgetCard keyInfo={keyInfo} />
              <KeyCard
                keyInfo={keyInfo}
                initialSecret={
                  keyToken(keyInfo) === newKeyIdentifier ? newKey : null
                }
                canReveal={
                  !!config?.save_api_keys_in_db && !!keyInfo.secret_available
                }
                onHide={() => setNewKey(null)}
                action={index === 0 ? regenerateAction : null}
              />
            </div>
          ))
        )}
        {hasKey && keys.isError && (
          <p className="text-sm text-ink-4">
            Key information is unavailable. Retry before creating or replacing a
            key.
          </p>
        )}
        {config?.my_key_text?.trim() && (
          <p
            aria-label="My key guidance"
            className="whitespace-pre-wrap break-words text-sm text-ink-3"
          >
            {config.my_key_text}
          </p>
        )}
      </div>
      <aside
        aria-label="Key status"
        className="flex flex-[1_1_280px] flex-col gap-3.5"
      >
        <StatusCard keyInfo={keyList[0]} status={statusLabel} />
        {hasKey && <DetailsCard keys={keyList} />}
        <LinkCard links={helpfulLinks} />
      </aside>
    </div>
  );

  if (!adminLayout) {
    const topLink =
      "rounded-md px-2 py-1.5 text-ink-3 no-underline transition-colors duration-150 hover:bg-ink/[0.06] hover:text-ink";
    return (
      <div className="min-h-screen bg-canvas text-ink">
        <header className="sticky top-0 z-20 border-b border-line-soft bg-card/80 text-ink backdrop-blur-xl backdrop-saturate-150">
          <div className="mx-auto flex max-w-[1040px] flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:px-8">
            <Link to="/my-key" className="no-underline">
              <BrandMark logoUrl={config?.logo_url} />
            </Link>
            <nav
              aria-label="Primary navigation"
              className="ml-auto flex flex-wrap items-center justify-end gap-x-2 gap-y-1 text-sm"
            >
              {demoSwitch}
              {analyticsEnabled &&
                (section === "/analytics" ? (
                  <Link to="/my-key" className={topLink}>
                    My key
                  </Link>
                ) : (
                  <Link to="/analytics" className={topLink}>
                    Analytics
                  </Link>
                ))}
              {config?.setup_guide_url && (
                <a
                  href={config.setup_guide_url}
                  target="_blank"
                  rel="noreferrer"
                  className={topLink}
                >
                  Setup guide
                </a>
              )}
              <span
                aria-hidden="true"
                className="mx-1 hidden h-5 w-px bg-line sm:block"
              />
              <UserMenu
                email={user?.email}
                role={roleLabel}
                onSignOut={signOut}
                apiDocsUrl={isAdmin ? config?.api_docs_url : undefined}
              />
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-[1080px] px-4 pb-14 pt-9 sm:px-8">
          {section === "/analytics" ? <PersonalAnalytics /> : myKey}
        </main>
      </div>
    );
  }

  const navGroups: NavGroup[] = [
    {
      label: "Workspace",
      items: [
        { to: "/my-key", label: "My key", icon: KeyRound },
        ...(analyticsEnabled
          ? [{ to: "/analytics", label: "Analytics", icon: Activity }]
          : []),
      ],
    },
    {
      label: "Manage",
      items: [
        { to: "/organization", label: "Organization", icon: LayoutGrid },
        ...(isAdmin
          ? [
              { to: "/teams", label: "Teams", icon: Users },
              { to: "/keys", label: "Keys", icon: List },
              { to: "/users", label: "People", icon: UserIcon },
            ]
          : []),
      ],
    },
    ...(isAdmin
      ? [
          {
            label: "System",
            items: [
              { to: "/audit", label: "Audit log", icon: Clock3 },
              {
                to: "/status",
                label: "Status",
                icon: Activity,
                dot: systemStatus.data
                  ? systemStatus.data.ready
                    ? ("ok" as const)
                    : ("bad" as const)
                  : undefined,
              },
            ],
          },
        ]
      : []),
  ];

  return (
    <div className="min-h-screen bg-canvas text-ink md:flex md:h-screen md:overflow-hidden">
      <AdminSidebar
        groups={navGroups}
        logoUrl={config?.logo_url}
        email={user?.email}
        role={roleLabel}
        onSignOut={signOut}
        apiDocsUrl={isAdmin ? config?.api_docs_url : undefined}
        extra={demoSwitch}
      />
      <div className="min-w-0 flex-1 md:flex md:flex-col">
        <main className="min-w-0 flex-1 md:overflow-y-auto">
          <Suspense
            fallback={
              <div className="mx-auto w-full max-w-6xl px-4 py-7 sm:px-8">
                <LoadingBlock label="Loading page…" className="h-64" />
              </div>
            }
          >
            {section === "/organization" && canViewOrganization ? (
              <AdminOrganization
                budgetsEnabled={!!config?.hierarchical_budgets_enabled}
                email={user?.email}
                isAdmin={isAdmin}
              />
            ) : section === "/my-key" || section === "/analytics" ? (
              <div className="mx-auto max-w-[1080px] px-4 pb-14 pt-9 sm:px-8">
                {section === "/analytics" ? <PersonalAnalytics /> : myKey}
              </div>
            ) : (
              <div className="mx-auto w-full max-w-6xl px-4 py-7 sm:px-8">
                {section === "/users" && isAdmin ? (
                  <AdminUsers localUsersEnabled={localUsersEnabled} />
                ) : section === "/teams" && isAdmin ? (
                  <AdminTeams budgetWindows={config?.team_budget_windows} />
                ) : section === "/keys" && isAdmin ? (
                  <AdminKeys
                    saveApiKeysInDb={config?.save_api_keys_in_db}
                    enterpriseEnabled={config?.litellm_enterprise_enabled}
                  />
                ) : section === "/status" && isAdmin ? (
                  <AdminStatus />
                ) : section === "/audit" && isAdmin ? (
                  <AdminAudit />
                ) : null}
              </div>
            )}
          </Suspense>
        </main>
      </div>
    </div>
  );
}
