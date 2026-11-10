import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ModelBudget } from "../types";

export interface ModelBudgetRow {
  model: string;
  amount: string;
  period: string;
}

export function parseModelBudgets(
  rows: ModelBudgetRow[],
): Record<string, ModelBudget> {
  const entries = rows.map(({ model, amount, period }) => {
    const name = model.trim();
    if (!name || name.length > 256)
      throw new Error(
        "Enter a model name for each budget (up to 256 characters).",
      );
    if (
      !amount.trim() ||
      !Number.isFinite(Number(amount)) ||
      Number(amount) < 0
    )
      throw new Error(
        "Model budgets must be finite dollar amounts of zero or more.",
      );
    if (
      period.trim().length > 32 ||
      !/^[1-9][0-9]*(s|m|h|d)$/.test(period.trim())
    )
      throw new Error(
        "Enter a positive model reset period, for example 2h or 30d.",
      );
    return [
      name,
      { budget_limit: Number(amount), time_period: period.trim() },
    ] as const;
  });
  if (new Set(entries.map(([name]) => name)).size !== entries.length)
    throw new Error("Each model can have only one budget.");
  if (entries.length > 100)
    throw new Error("At most 100 model budgets may be supplied.");
  return Object.fromEntries(entries);
}

const inputClass =
  "min-w-0 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900";

export default function ModelBudgetEditor({
  rows,
  onChange,
  saved,
}: {
  rows: ModelBudgetRow[] | undefined;
  onChange: (rows: ModelBudgetRow[] | undefined) => void;
  saved?: Record<string, ModelBudget> | null;
}) {
  const catalog = useQuery({
    queryKey: ["admin-models"],
    queryFn: () => api.listModels(),
    staleTime: 60_000,
  });
  function change(index: number, field: keyof ModelBudgetRow, value: string) {
    onChange(
      rows?.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );
  }
  return (
    <fieldset className="min-w-0 space-y-3 rounded-xl border border-slate-200 p-3 text-xs text-slate-700 sm:col-span-2">
      <legend className="px-1 font-semibold">Per-model budgets</legend>
      <p>
        Model spending also counts toward the overall key budget. Each model has
        its own reset period.
      </p>
      {saved &&
        Object.entries(saved).map(([model, budget]) => (
          <p key={model} className="break-words">
            {model}: ${budget.budget_limit} every {budget.time_period}
          </p>
        ))}
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={rows !== undefined}
          onChange={(event) =>
            onChange(
              event.target.checked
                ? Object.entries(saved ?? {}).map(([model, budget]) => ({
                    model,
                    amount: String(budget.budget_limit),
                    period: budget.time_period,
                  }))
                : undefined,
            )
          }
        />
        Replace per-model budgets
      </label>
      {rows !== undefined && (
        <>
          <p className="text-amber-700">
            This replaces all per-model budgets on every selected key. Models
            omitted here lose their separate limit. Overall key budgets stay
            unchanged.
          </p>
          {rows.length === 0 && (
            <p>All per-model limits will be removed from the selected keys.</p>
          )}
          <datalist id="key-budget-models">
            {(catalog.data?.models ?? []).map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
          {rows.map((row, index) => (
            <div
              key={index}
              className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
            >
              <label className="min-w-0">
                Budget model {index + 1}
                <input
                  className={inputClass}
                  list="key-budget-models"
                  value={row.model}
                  maxLength={256}
                  required
                  onChange={(event) =>
                    change(index, "model", event.target.value)
                  }
                />
              </label>
              <label className="min-w-0">
                Model budget {index + 1} (USD)
                <input
                  className={inputClass}
                  type="number"
                  min="0"
                  step="any"
                  required
                  value={row.amount}
                  onChange={(event) =>
                    change(index, "amount", event.target.value)
                  }
                />
              </label>
              <label className="min-w-0">
                Model reset period {index + 1}
                <input
                  className={inputClass}
                  placeholder="For example 2h"
                  maxLength={32}
                  required
                  value={row.period}
                  onChange={(event) =>
                    change(index, "period", event.target.value)
                  }
                />
              </label>
              <button
                type="button"
                aria-label={`Remove model budget ${index + 1}`}
                className="self-end rounded border border-slate-300 px-3 py-2"
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            disabled={rows.length >= 100}
            className="rounded border border-slate-300 px-3 py-2 disabled:opacity-50"
            onClick={() =>
              onChange([...rows, { model: "", amount: "", period: "" }])
            }
          >
            Add model budget
          </button>
          <p className="text-slate-500">
            Periods: seconds (s), minutes (m), hours (h), or days (d). Requires
            a valid LiteLLM Enterprise license.
          </p>
        </>
      )}
    </fieldset>
  );
}
