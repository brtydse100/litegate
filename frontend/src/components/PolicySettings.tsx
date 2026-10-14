import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { KeyInfo, TeamInfo, ModelSelection } from "../types";

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
}: {
  value: ModelSelection;
  onChange: (value: ModelSelection) => void;
  knownModels?: string[];
  status?: string;
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
    <fieldset className="space-y-2 rounded-md border border-slate-300 p-3 text-xs text-gray-400 sm:col-span-2">
      <legend className="px-1">Allowed models</legend>
      {status && (
        <p>
          {status}. Choose a replacement model policy for the selected keys.
        </p>
      )}
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={value.all}
          onChange={(event) =>
            onChange({ models: [], all: event.target.checked })
          }
        />
        All allowed models
      </label>
      <div className="grid max-h-48 gap-2 overflow-y-auto sm:grid-cols-2">
        {options.map((model) => (
          <label key={model} className="flex items-center gap-2 break-all">
            <input
              type="checkbox"
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
            {model}
          </label>
        ))}
      </div>
      {catalog.isPending && <p>Loading models...</p>}
      {catalog.isError && (
        <p className="text-xs text-amber-600">
          Model choices are unavailable. Saved selections are still shown.
        </p>
      )}
      {!status && !value.all && !value.models.length && (
        <p className="text-amber-600">
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
