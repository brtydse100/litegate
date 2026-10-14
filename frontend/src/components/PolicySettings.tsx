import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { KeyInfo, TeamInfo } from "../types";

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
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  className: string;
}) {
  const catalog = useQuery({
    queryKey: ["admin-models"],
    queryFn: () => api.listModels(),
    staleTime: 60_000,
  });
  const selected = value
    .split(/[\n,]/)
    .map((model) => model.trim())
    .filter(Boolean);
  return (
    <div className="space-y-1">
      <select
        aria-label="Add available model"
        value=""
        className={className}
        onChange={(event) => {
          if (event.target.value && !selected.includes(event.target.value))
            onChange([...selected, event.target.value].join(", "));
        }}
      >
        <option value="">
          {catalog.isPending ? "Loading models..." : "Choose a model to add"}
        </option>
        {(catalog.data?.models ?? []).map((model) => (
          <option key={model} value={model} disabled={selected.includes(model)}>
            {model}
          </option>
        ))}
      </select>
      {catalog.isError && (
        <p className="text-xs text-amber-600">
          Model choices are unavailable. You can still enter model names.
        </p>
      )}
    </div>
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
}: {
  settings: KeyInfo | TeamInfo;
}) {
  const entries = [
    ["Maximum budget", limit(settings.max_budget, true)],
    [
      "Budget reset",
      settings.budget_duration === undefined
        ? "Not provided"
        : settings.budget_duration || "No reset",
    ],
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
          <dt className="text-gray-500">{label}</dt>
          <dd className="break-words text-gray-300">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
