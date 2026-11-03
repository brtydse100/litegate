import { useState } from "react";
import type { KeyInfo, ModelSelection } from "../types";

type Field =
  | "alias"
  | "budget"
  | "budgetDuration"
  | "tpm"
  | "rpm"
  | "duration"
  | "blockedSetting";

const fields: Field[] = [
  "alias",
  "budget",
  "budgetDuration",
  "tpm",
  "rpm",
  "duration",
  "blockedSetting",
];

function savedValue(key: KeyInfo, field: Field): string | null | undefined {
  switch (field) {
    case "alias":
      return key.key_alias;
    case "budget":
      return key.max_budget == null ? key.max_budget : String(key.max_budget);
    case "budgetDuration":
      return key.budget_duration;
    case "tpm":
      return key.tpm_limit == null ? key.tpm_limit : String(key.tpm_limit);
    case "rpm":
      return key.rpm_limit == null ? key.rpm_limit : String(key.rpm_limit);
    case "blockedSetting":
      return typeof key.blocked === "boolean" ? String(key.blocked) : undefined;
    // Expiry is an absolute timestamp, not a new relative lifetime.
    case "duration":
      return "";
  }
}

export function useKeySettingsForm(selected: string[], knownKeys: KeyInfo[]) {
  const selection = JSON.stringify([...selected].sort());
  const [draft, setDraft] = useState<{
    selection: string;
    values: Partial<Record<Field, string>>;
    models?: ModelSelection;
  }>({ selection, values: {} });
  // A different target must never inherit edits intended for the previous one.
  if (draft.selection !== selection) setDraft({ selection, values: {} });
  const edits = draft.selection === selection ? draft.values : {};
  const complete = selected.length > 0 && knownKeys.length === selected.length;
  const saved = {} as Record<Field, string>;
  const placeholders = {} as Record<Field, string>;
  for (const field of fields) {
    const values = knownKeys.map((key) => savedValue(key, field));
    const shared = complete && values.every((value) => value === values[0]);
    saved[field] = shared ? (values[0] ?? "") : "";
    placeholders[field] = !selected.length
      ? "No change"
      : !complete
        ? "Current values unavailable"
        : !shared
          ? "Mixed values"
          : values[0] === undefined
            ? "Not provided"
            : values[0] === null && ["budget", "tpm", "rpm"].includes(field)
              ? "Unlimited"
              : field === "blockedSetting"
                ? values[0] === "true"
                  ? "Current: Blocked"
                  : "Current: Active"
                : values[0] ||
                  (field === "budgetDuration"
                    ? "No reset"
                    : field === "alias"
                      ? "No alias"
                      : "No change");
  }
  const modelLists = knownKeys.map((key) =>
    Array.isArray(key.models)
      ? [...new Set(key.models)].sort()
      : key.models === null
        ? []
        : undefined,
  );
  const sharedModels =
    complete &&
    modelLists[0] !== undefined &&
    modelLists.every(
      (models) => JSON.stringify(models) === JSON.stringify(modelLists[0]),
    );
  const savedModels = sharedModels ? modelLists[0]! : [];
  const modelDraft = draft.selection === selection ? draft.models : undefined;
  const modelSelection = modelDraft ?? {
    models: savedModels,
    all: sharedModels && savedModels.length === 0,
  };
  const modelsChanged =
    modelDraft !== undefined &&
    (!sharedModels ||
      modelDraft.all !== (savedModels.length === 0) ||
      JSON.stringify([...modelDraft.models].sort()) !==
        JSON.stringify(savedModels));
  return {
    modelSelection,
    modelsChanged,
    modelStatus:
      modelDraft || sharedModels
        ? undefined
        : !selected.length
          ? "No change"
          : complete && modelLists.every((models) => models !== undefined)
            ? "Mixed values"
            : "Current values unavailable",
    setModels: (models: ModelSelection) =>
      setDraft((current) => ({
        selection,
        values: current.selection === selection ? current.values : {},
        models,
      })),
    values: { ...saved, ...edits },
    placeholder: (field: Field) => placeholders[field],
    isChanged: (field: Field) =>
      edits[field] !== undefined && edits[field] !== saved[field],
    setValue: (field: Field, value: string) =>
      setDraft((current) => ({
        selection,
        values: {
          ...(current.selection === selection ? current.values : {}),
          [field]: value,
        },
        models: current.selection === selection ? current.models : undefined,
      })),
  };
}
