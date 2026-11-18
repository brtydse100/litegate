import { useState } from "react";
import PerUserLimitEditor from "./PerUserLimitEditor";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BudgetGroup, BudgetView } from "../types/budgets";
import EmailAddress from "./EmailAddress";
import DismissibleMessage from "./DismissibleMessage";
import { formatUsd } from "../formatUsd";

const money = (value: number | null) =>
  value === null ? "Unavailable" : formatUsd(value);
const inputClass =
  "w-32 rounded border border-slate-300 bg-white p-2 text-sm text-slate-900";

function BudgetGroupEditor({
  group,
  revision,
}: {
  group: BudgetGroup;
  revision: number;
}) {
  const client = useQueryClient();
  // Drafts live per group (editors are keyed by group id, not revision), so a
  // save elsewhere never discards them. A saved field reverts to server data.
  const [envelope, setEnvelope] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const mutation = useMutation({
    mutationFn: ({ user, amount }: { user?: string; amount: string | null }) =>
      user
        ? api.setUserBudget(group.id, user, revision, amount)
        : api.setGroupBudget(group.id, revision, amount ?? "0"),
    onSuccess: (result, { user }) => {
      client.setQueryData(["organization-budgets"], result);
      if (user)
        setOverrides((previous) => {
          const next = { ...previous };
          delete next[user];
          return next;
        });
      else setEnvelope(null);
    },
    // A conflict means the revision or allocations changed; reload them so
    // the retained draft can be reviewed and saved against current data.
    onError: () =>
      void client.invalidateQueries({ queryKey: ["organization-budgets"] }),
  });
  const envelopeValue = envelope ?? String(group.assigned);
  return (
    <article className="space-y-4 rounded-lg border border-slate-200 bg-white p-5">
      <h3 className="font-semibold text-slate-950">{group.name}</h3>
      {group.allocation_error && (
        <p role="alert" className="text-sm text-red-600">
          {group.allocation_error}
        </p>
      )}
      <p className="text-xs text-slate-500">
        {group.path.join(" / ")}
        {group.duration ? ` · ${group.duration}` : " · No automatic reset"}
      </p>
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        {[
          ["Assigned", group.assigned],
          ["Allocated", group.allocated],
          ["Unallocated", group.remainder],
          ["Used", group.used],
          ["Remaining", group.remaining],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd>{money(value as number | null)}</dd>
          </div>
        ))}
      </dl>
      <PerUserLimitEditor group={group} />
      {group.can_edit_envelope ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate({ amount: envelopeValue });
          }}
          className="flex flex-wrap items-end gap-2"
        >
          <label className="text-xs text-slate-600">
            {group.parent_id ? "Child allocation" : "Assigned budget"}
            <input
              aria-label={`${group.name} ${group.parent_id ? "child allocation" : "assigned budget"}`}
              className={`${inputClass} ml-2`}
              value={envelopeValue}
              onChange={(event) => setEnvelope(event.target.value)}
              type="number"
              min="0"
              step="0.000001"
              required
            />
          </label>
          <button
            disabled={mutation.isPending}
            className="rounded bg-indigo-600 px-3 py-2 text-sm text-white"
          >
            Save {group.name} budget
          </button>
        </form>
      ) : (
        <p className="text-xs text-slate-500">
          This assigned total is read-only. Redistribute it among members and
          child teams below. A parent or system administrator assigns the total.
        </p>
      )}
      <ul className="space-y-3">
        {group.users.map((user) => (
          <li
            key={user.user_id}
            className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3"
          >
            <div className="min-w-0 flex-1">
              {user.email ? (
                <EmailAddress email={user.email} />
              ) : (
                <span className="break-all">{user.user_id}</span>
              )}
              <p className="text-xs text-slate-500">
                {user.mode === "automatic"
                  ? "Automatic"
                  : user.mode === "fixed"
                    ? "Fixed per-user"
                    : "Manual override"}
                : {money(user.allocation)}
              </p>
            </div>
            {user.can_edit && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const value =
                    overrides[user.user_id] ??
                    (user.override == null ? "" : String(user.override));
                  mutation.mutate({
                    user: user.user_id,
                    amount: value === "" ? null : value,
                  });
                }}
                className="flex flex-wrap gap-2"
              >
                <input
                  aria-label={`Budget override for ${user.email || user.user_id}`}
                  className={inputClass}
                  value={
                    overrides[user.user_id] ??
                    (user.override == null ? "" : String(user.override))
                  }
                  onChange={(event) =>
                    setOverrides((previous) => ({
                      ...previous,
                      [user.user_id]: event.target.value,
                    }))
                  }
                  placeholder="Automatic"
                  type="number"
                  min="0"
                  step="0.000001"
                />
                <button
                  disabled={mutation.isPending}
                  className="rounded border border-slate-300 px-3 py-2 text-sm"
                >
                  Save user budget
                </button>
              </form>
            )}
          </li>
        ))}
      </ul>
      {mutation.error && (
        <DismissibleMessage
          role="alert"
          messageKey={mutation.error.message}
          className="text-sm text-red-600"
        >
          {mutation.error.message}
        </DismissibleMessage>
      )}
    </article>
  );
}

export default function BudgetManager() {
  const query = useQuery<BudgetView>({
    queryKey: ["organization-budgets"],
    queryFn: api.organizationBudgets,
  });
  if (query.isPending) return <p role="status">Loading budget allocations…</p>;
  if (query.isError)
    return (
      <div role="alert">
        Could not load budget allocations.{" "}
        <button onClick={() => void query.refetch()} className="underline">
          Retry
        </button>
      </div>
    );
  const data = query.data;
  return (
    <section className="mt-8 space-y-5" aria-label="Budget management">
      <h2 className="text-xl font-semibold text-slate-950">Budget planning</h2>
      {data.applied ? (
        <div
          role="status"
          className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900"
        >
          Enforced: these allowances cap members' keys. Changes and new members
          apply within about a minute.
        </div>
      ) : (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p>
            These allocations are proposals, not applied to inference. Existing
            enforced policies remain active.
          </p>
          <ul className="mt-2 list-inside list-disc">
            {data.capability.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <button
            disabled
            className="mt-3 rounded border border-amber-300 px-3 py-2 disabled:opacity-60"
          >
            Activate budget enforcement
          </button>
        </div>
      )}
      <p className="text-sm text-slate-600">
        Child allocations and manual overrides are reserved first. The remainder
        is shared equally by other signed-in direct members, never above the
        group's per-user limit. Members of groups without a budget keep their
        fixed per-user allowance. Clear a user override to restore automatic
        allocation.
      </p>
      {data.groups.map((group) => (
        <BudgetGroupEditor
          key={group.id}
          group={group}
          revision={data.revision}
        />
      ))}
    </section>
  );
}
