import { useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "../../api/client";
import type { BudgetGroup, BudgetUser, BudgetView } from "../../types/budgets";
import EmailAddress from "../EmailAddress";
import DismissibleMessage from "../DismissibleMessage";
import { metricValue } from "../OrganizationCharts";

const money = (value: number | null) =>
  value === null ? "No cap" : metricValue(value, "spend");
const modes: Record<BudgetUser["mode"], string> = {
  automatic: "Automatic",
  manual: "Manual override",
  fixed: "Fixed per-user",
};

/**
 * Members of some groups with their spend and allowance. With budget
 * planning, each allowance is editable in place where the viewer may.
 */
export default function PeopleTable({
  nodeIds,
  title,
  totalUsers,
  budgets,
  actions,
  standalone = false,
}: {
  nodeIds: string[];
  title: string;
  totalUsers?: number;
  budgets?: BudgetView;
  actions?: ReactNode;
  /** A page section of its own rather than part of the usage report. */
  standalone?: boolean;
}) {
  const client = useQueryClient();
  const nodeKey = nodeIds.join(",");
  const [page, setPage] = useState(1);
  const [pageNode, setPageNode] = useState(nodeKey);
  if (pageNode !== nodeKey) {
    setPageNode(nodeKey);
    setPage(1);
  }
  const users = useQuery({
    queryKey: ["organization-users", nodeKey, page],
    queryFn: () => api.organizationUsers(nodeIds, page),
    staleTime: 60000,
    refetchInterval: 60000,
  });
  // Each member's planned allowance and the group it is planned in.
  const planned = new Map<string, { group: BudgetGroup; user: BudgetUser }>();
  budgets?.groups.forEach((group) =>
    group.users.forEach((user) => planned.set(user.user_id, { group, user })),
  );
  // Drafts are kept per member, so saving one never discards another.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: ({
      group,
      user,
      amount,
    }: {
      group: string;
      user: string;
      amount: string | null;
    }) => api.setUserBudget(group, user, budgets!.revision, amount),
    onSuccess: (view, { user }) => {
      client.setQueryData(["organization-budgets"], view);
      setDrafts((previous) => {
        const next = { ...previous };
        delete next[user];
        return next;
      });
    },
    // A conflict means the revision or allocations changed; reload them so
    // the retained draft can be reviewed and saved against current data.
    onError: () =>
      void client.invalidateQueries({ queryKey: ["organization-budgets"] }),
  });
  const shownGroups = new Map(
    (users.data?.users ?? [])
      .map((user) => planned.get(user.user_id)?.group)
      .filter((group): group is BudgetGroup => !!group)
      .map((group) => [group.id, group]),
  );
  const allocationErrors = [...shownGroups.values()].filter(
    (group) => group.allocation_error,
  );

  return (
    <section
      aria-label={title}
      className={`overflow-hidden border border-line ${
        standalone ? "rounded-xl bg-card" : "rounded-[10px]"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-line px-4 py-3">
        <h2
          className={`flex items-center gap-2 font-semibold text-ink ${standalone ? "text-base" : "text-sm"}`}
        >
          <Users size={16} aria-hidden="true" /> {title}{" "}
          <span className="font-normal text-ink-4">
            ({users.data?.total ?? totalUsers ?? "…"})
          </span>
        </h2>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {budgets && standalone && (
        <p className="border-b border-line-soft px-4 py-2.5 text-xs text-ink-4">
          {budgets.applied
            ? "Enforced: these allowances cap members' keys. Changes apply within about a minute."
            : `Allowances are proposals and do not cap keys yet.${
                budgets.capability.reasons.length
                  ? ` ${budgets.capability.reasons.join(" ")}`
                  : ""
              }`}{" "}
          Leave an allowance empty for an equal share of the team's budget.
        </p>
      )}
      {allocationErrors.map((group) => (
        <p
          key={group.id}
          role="alert"
          className="border-b border-line-soft bg-danger-tint px-4 py-2.5 text-xs text-danger"
        >
          {group.name}: {group.allocation_error}
        </p>
      ))}
      {save.error && (
        <DismissibleMessage
          role="alert"
          messageKey={save.error.message}
          className="border-b border-line-soft bg-danger-tint px-4 py-2.5 text-xs text-danger"
        >
          {save.error.message}
        </DismissibleMessage>
      )}
      {users.error ? (
        <p role="alert" className="p-4 text-sm text-danger">
          {users.error.message}{" "}
          <button
            type="button"
            className="font-semibold underline"
            onClick={() => void users.refetch()}
          >
            Retry users
          </button>
        </p>
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-canvas text-ink-4">
              <tr>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Team</th>
                <th className="px-4 py-3">Budget-period spend</th>
                <th className="px-4 py-3">Per-key allowance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {users.data?.users.map((user) => {
                const plan = planned.get(user.user_id);
                const name = user.email || user.user_id;
                const value =
                  drafts[user.user_id] ??
                  (plan?.user.override == null
                    ? ""
                    : String(plan.user.override));
                return (
                  <tr key={user.user_id}>
                    <td className="min-w-[13rem] px-4 py-3">
                      {user.email ? (
                        <EmailAddress
                          email={user.email}
                          className="font-medium text-ink-2"
                        />
                      ) : (
                        <p className="break-all font-medium text-ink-2">
                          {user.user_id}
                        </p>
                      )}
                      {user.email && (
                        <p className="mt-1 text-ink-4">{user.user_id}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-ink-3">
                      {user.path.join(" › ")}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-ink-2">
                        {user.budget_spend === null
                          ? "Unavailable"
                          : metricValue(user.budget_spend, "spend")}
                      </p>
                      {user.sync_error && (
                        <p className="mt-1 text-sand-ink">{user.sync_error}</p>
                      )}
                    </td>
                    <td className="min-w-[15rem] px-4 py-3">
                      {plan ? (
                        <>
                          <p className="text-ink-2">
                            {modes[plan.user.mode]}:{" "}
                            {plan.user.allocation === null
                              ? "Unavailable"
                              : metricValue(plan.user.allocation, "spend")}
                          </p>
                          {plan.user.can_edit ? (
                            <form
                              onSubmit={(event) => {
                                event.preventDefault();
                                save.mutate({
                                  group: plan.group.id,
                                  user: user.user_id,
                                  amount: value === "" ? null : value,
                                });
                              }}
                              className="mt-1.5 flex items-center gap-2"
                            >
                              <span className="flex h-9 w-28 items-center rounded-lg border border-line-input bg-card px-2.5 focus-within:outline focus-within:outline-2 focus-within:outline-blue">
                                <span aria-hidden="true" className="text-ink-4">
                                  $
                                </span>
                                <input
                                  aria-label={`Budget override for ${name}`}
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  placeholder="Automatic"
                                  value={value}
                                  onChange={(event) =>
                                    setDrafts((previous) => ({
                                      ...previous,
                                      [user.user_id]: event.target.value,
                                    }))
                                  }
                                  className="w-full min-w-0 border-0 bg-transparent px-1 text-xs text-ink focus:outline-none"
                                />
                              </span>
                              <button
                                disabled={save.isPending}
                                aria-label={`Save allowance for ${name}`}
                                className="h-9 rounded-lg border border-line-input px-3 font-semibold text-ink-2 hover:bg-canvas disabled:opacity-50"
                              >
                                Save
                              </button>
                            </form>
                          ) : (
                            <p className="mt-1 text-ink-4">
                              Set by a parent team or a system administrator
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="text-ink-2">{money(user.per_user)}</p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!users.isPending && !users.data?.users.length && (
            <p className="p-6 text-center text-sm text-ink-4">
              No mapped users in this group yet. SSO users appear after signing
              in.
            </p>
          )}
        </div>
      )}
      <div className="flex items-center justify-between border-t border-line px-4 py-3 text-xs text-ink-4">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          className="min-h-9 px-2 disabled:opacity-40"
        >
          Previous
        </button>
        <span>
          Page {page} of {users.data?.total_pages ?? 1}
        </span>
        <button
          type="button"
          disabled={page >= (users.data?.total_pages ?? 1)}
          onClick={() => setPage(page + 1)}
          className="min-h-9 px-2 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </section>
  );
}
