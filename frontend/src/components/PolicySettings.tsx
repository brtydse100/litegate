import { useQuery } from "@tanstack/react-query";
import { useId, type InputHTMLAttributes } from "react";
import { Minus, Plus } from "lucide-react";
import { api } from "../api/client";
import type { KeyInfo, TeamInfo, ModelSelection } from "../types";

export function NumericPolicyInput({
  label,
  value,
  onValueChange,
  disabled,
  ...props
}: Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "value" | "onChange" | "className" | "min"
> & {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
}) {
  const generatedId = useId();
  const id = props.id ?? generatedId;
  const current = Number(value || 0);
  function adjust(delta: number) {
    const next = Math.max(0, current + delta);
    if (Number.isFinite(next)) onValueChange(String(next));
  }
  return (
    <div className="space-y-1 text-xs text-ink-3">
      <label htmlFor={id}>{label}</label>
      <div className="flex overflow-hidden rounded-md border border-line-input bg-card shadow-sm focus-within:border-blue focus-within:ring-2 focus-within:ring-blue/20">
        <input
          {...props}
          id={id}
          type="number"
          min="0"
          value={value}
          disabled={disabled}
          onChange={(event) => onValueChange(event.target.value)}
          className="policy-number-input min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-4 disabled:opacity-50"
        />
        <div className="flex items-stretch border-l border-line">
          <button
            type="button"
            aria-label={`Decrease ${label}`}
            disabled={disabled || current <= 0}
            onClick={() => adjust(-1)}
            className="px-2 text-ink-3 hover:bg-ink/[0.06] focus-visible:outline-blue disabled:opacity-30"
          >
            <Minus size={14} />
          </button>
          <button
            type="button"
            aria-label={`Increase ${label}`}
            disabled={disabled}
            onClick={() => adjust(1)}
            className="border-l border-line px-2 text-ink-3 hover:bg-ink/[0.06] focus-visible:outline-blue disabled:opacity-30"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

const durationChoices = [
  ["1h", "Hourly"],
  ["1d", "Daily"],
  ["7d", "Weekly"],
  ["30d", "Every 30 days"],
  ["1mo", "Monthly"],
  ["90d", "Every 90 days"],
] as const;

export function DurationChoices({ id }: { id: string }) {
  return (
    <datalist id={id}>
      {durationChoices.map(([value, label]) => (
        <option key={value} value={value}>
          {label}
        </option>
      ))}
    </datalist>
  );
}

export function ModelChoices({
  value,
  onChange,
  knownModels = [],
  status,
  scrollable = true,
}: {
  value: ModelSelection;
  onChange: (value: ModelSelection) => void;
  knownModels?: string[];
  status?: string;
  scrollable?: boolean;
}) {
  const catalog = useQuery({
    queryKey: ["admin-models"],
    queryFn: () => api.listModels(),
    staleTime: 60_000,
  });
  const options = [
    ...new Set([
      ...(catalog.data?.models ?? []),
      ...knownModels,
      ...value.models,
    ]),
  ].sort();
  return (
    <fieldset className="min-w-0 space-y-3 rounded-xl border border-line-soft bg-card p-3 text-xs text-ink-2 sm:col-span-2">
      <legend className="px-1 font-semibold">Allowed models</legend>
      {status && (
        <p className="text-ink-4">
          {status}. Choose a replacement model policy for the selected keys.
        </p>
      )}
      <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 hover:bg-ink/[0.06]">
        <input
          type="checkbox"
          className="h-4 w-4 shrink-0 accent-blue"
          checked={value.all}
          onChange={(event) =>
            onChange({ models: [], all: event.target.checked })
          }
        />
        All allowed models
      </label>
      <div
        className={`grid gap-1 border-t border-line-soft pt-2 sm:grid-cols-2 ${scrollable ? "max-h-48 overflow-y-auto" : ""}`}
      >
        {options.map((model) => (
          <label
            key={model}
            data-selected={!value.all && value.models.includes(model)}
            className="policy-model-option flex min-w-0 cursor-pointer items-start gap-2 rounded-md border border-transparent px-2 py-2 hover:bg-ink/[0.06]"
          >
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 shrink-0 accent-blue"
              checked={!value.all && value.models.includes(model)}
              onChange={(event) =>
                onChange({
                  all: false,
                  models: event.target.checked
                    ? [...value.models, model]
                    : value.models.filter((item) => item !== model),
                })
              }
            />
            <span className="min-w-0 break-all leading-5">{model}</span>
          </label>
        ))}
      </div>
      <p className="text-xs text-ink-4">
        {value.all ? "All models allowed" : `${value.models.length} selected`}
      </p>
      {catalog.isPending && <p>Loading models...</p>}
      {catalog.isError && (
        <p className="text-xs text-orange-ink">
          Model choices are unavailable. Saved selections are still shown.
        </p>
      )}
      {!status && !value.all && !value.models.length && (
        <p className="text-orange-ink">
          Select at least one model or allow all models.
        </p>
      )}
    </fieldset>
  );
}

function limit(value: number | null | undefined, money = false) {
  return value === undefined
    ? "Not provided"
    : value === null
      ? "Unlimited"
      : `${money ? "$" : ""}${value}`;
}

export function CurrentPolicySettings({
  settings,
  hideReset = false,
}: {
  settings: KeyInfo | TeamInfo;
  /** Scheduled budget windows replace the reset period on the Teams page. */
  hideReset?: boolean;
}) {
  const entries = [
    ["Maximum budget", limit(settings.max_budget, true)],
    ...(hideReset
      ? []
      : [
          [
            "Budget reset",
            settings.budget_duration === undefined
              ? "Not provided"
              : settings.budget_duration || "No reset",
          ],
        ]),
    [
      "Allowed models",
      Array.isArray(settings.models)
        ? settings.models.join(", ") || "All allowed models"
        : settings.models === null
          ? "All allowed models"
          : "Not provided",
    ],
    ["TPM limit", limit(settings.tpm_limit)],
    ["RPM limit", limit(settings.rpm_limit)],
    [
      "Status",
      settings.blocked === undefined
        ? "Not provided"
        : settings.blocked
          ? "Blocked"
          : "Active",
    ],
    ...("expires" in settings
      ? [["Expires", settings.expires || "No expiry"]]
      : []),
  ];
  return (
    <dl className="grid gap-2 text-xs sm:grid-cols-2">
      {entries.map(([label, value]) => (
        <div key={label}>
          <dt className="text-ink-4">{label}</dt>
          <dd className="break-words text-ink-2">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
