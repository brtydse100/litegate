import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BudgetGroup } from "../types/budgets";
import DismissibleMessage from "./DismissibleMessage";
import { formatUsd } from "../formatUsd";

const describe = (value: number | null) =>
  value === null ? "No limit" : formatUsd(value);

/** A global administrator's per-user ceiling for one organization group. */
export default function PerUserLimitEditor({ group }: { group: BudgetGroup }) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (amount: string | null) =>
      api.setGroupPerUser(group.id, amount),
    onSuccess: () => {
      setDraft(null);
      void client.invalidateQueries({ queryKey: ["organization-budgets"] });
      void client.invalidateQueries({ queryKey: ["teams"] });
    },
  });
  const overridden = group.per_user_override !== null;
  const source = overridden
    ? `set here; configured ${describe(group.per_user_config)}`
    : "from configuration";
  if (!group.can_edit_per_user)
    return (
      <p className="text-xs text-slate-500">
        Per-user limit: {describe(group.per_user)} ({source})
      </p>
    );
  const value =
    draft ?? (group.per_user === null ? "" : String(group.per_user));
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate(value === "" ? null : value);
      }}
      className="flex flex-wrap items-end gap-2"
    >
      <label className="text-xs text-slate-600">
        Per-user limit
        <input
          aria-label={`${group.name} per-user limit`}
          className="ml-2 w-32 rounded border border-slate-300 bg-white p-2 text-sm text-slate-900"
          value={value}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="No limit"
          type="number"
          min="0"
          step="0.000001"
        />
      </label>
      <button
        disabled={mutation.isPending}
        className="rounded border border-slate-300 px-3 py-2 text-sm"
      >
        Save {group.name} per-user limit
      </button>
      {overridden && (
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate(null)}
          className="rounded px-3 py-2 text-sm text-indigo-600 underline"
        >
          Use configured value
        </button>
      )}
      <span className="text-xs text-slate-500">{source}</span>
      {mutation.error && (
        <DismissibleMessage
          role="alert"
          messageKey={mutation.error.message}
          className="w-full text-sm text-red-600"
        >
          {mutation.error.message}
        </DismissibleMessage>
      )}
    </form>
  );
}
