import { forwardRef, useId, useImperativeHandle, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { PolicySchemaKind } from "../types";
import type { FieldError } from "../api/client";
import {
  allowsNull,
  asSchema,
  inputSchema,
  editableValue,
  validateValue,
} from "./advancedPolicySchema";

export interface AdvancedPolicyHandle {
  read: () => Record<string, unknown>;
  setServerError: (error: unknown) => void;
}
interface Draft {
  text: string;
  clear: boolean;
}
const inputClass =
  "w-full rounded-md border border-line-input bg-card px-3 py-2 text-sm text-ink";
// Defense in depth: schema discovery never makes credentials or identity selectors editable.
const restrictedField =
  /(?:secret|password|api_key|authorization|credential)|^(?:key|token|team_id|user_id|organization_id|members|members_with_roles|spend)$/i;

const AdvancedPolicySettings = forwardRef<
  AdvancedPolicyHandle,
  {
    operation: PolicySchemaKind;
    excludedFields: string[];
    current?: Record<string, unknown>;
  }
>(function AdvancedPolicySettings({ operation, excludedFields, current }, ref) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, Draft>>({});
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const id = useId();
  const discovery = useQuery({
    queryKey: ["policy-schemas"],
    queryFn: () => api.policySchemas(),
    enabled: open,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const schema = discovery.data?.available
    ? discovery.data.schemas[operation]
    : undefined;
  const properties = asSchema(schema?.properties);
  const fields = Object.entries(properties).filter(
    ([name, value]) =>
      !excludedFields.includes(name) &&
      !restrictedField.test(name) &&
      !asSchema(value).readOnly,
  );
  useImperativeHandle(ref, () => ({
    setServerError(failure) {
      const errors =
        failure && typeof failure === "object" && "fieldErrors" in failure
          ? failure.fieldErrors
          : [];
      setFieldErrors(Array.isArray(errors) ? errors : []);
    },
    read() {
      const result: Record<string, unknown> = {};
      try {
        for (const [name, raw] of fields) {
          const edit = draft[name];
          if (!edit) continue;
          const field = asSchema(raw);
          const control = inputSchema(field);
          let value: unknown;
          if (edit.clear) {
            if (!allowsNull(field))
              throw new Error(`${name}: clearing is not allowed.`);
            value = null;
          } else if (Array.isArray(control.enum)) {
            if (!edit.text) throw new Error(`${name}: choose a value.`);
            value = JSON.parse(edit.text);
          } else if (control.type === "number" || control.type === "integer") {
            if (!edit.text.trim()) throw new Error(`${name}: enter a number.`);
            value = Number(edit.text);
          } else if (control.type === "boolean") {
            if (!edit.text) throw new Error(`${name}: choose true or false.`);
            value = edit.text === "true";
          } else if (control.type === "string") value = edit.text;
          else {
            try {
              value = JSON.parse(edit.text);
            } catch {
              throw new Error(`${name}: enter valid JSON.`);
            }
          }
          validateValue(value, field, name);
          result[name] = value;
        }
        setError("");
        setFieldErrors([]);
        return result;
      } catch (failure) {
        setError((failure as Error).message);
        throw failure;
      }
    },
  }));
  function change(name: string, value: Draft | undefined) {
    setError("");
    setFieldErrors((previous) =>
      previous.filter((failure) => failure.loc[2] !== name),
    );
    setDraft((previous) => {
      const next = { ...previous };
      if (value) next[name] = value;
      else delete next[name];
      return next;
    });
  }
  return (
    <details
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="rounded-lg border border-line-input p-3 sm:col-span-2"
    >
      <summary className="cursor-pointer text-sm font-medium text-ink-3">
        Advanced settings
      </summary>
      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-ink-4">
            Fields advertised by this LiteLLM installation. Enable each field to
            change it; untouched fields are preserved. JSON values replace the
            complete field.
          </p>
          {discovery.isFetching && (
            <p className="text-xs text-ink-4">Loading available settings...</p>
          )}
          {!discovery.isFetching && (!schema || discovery.isError) && (
            <div className="space-y-2 text-xs text-sand-ink">
              <p>
                Advanced settings are unavailable. Familiar controls remain
                available.
              </p>
              <button
                type="button"
                onClick={() => void discovery.refetch()}
                className="rounded border px-2 py-1"
              >
                Retry discovery
              </button>
            </div>
          )}
          {fields.map(([name, raw]) => {
            const field = asSchema(raw);
            const control = inputSchema(field);
            const edit = draft[name];
            const failures = fieldErrors.filter(
              (failure) =>
                failure.loc[1] === "advanced_settings" &&
                failure.loc[2] === name,
            );
            const accessibility = {
              "aria-invalid": failures.length ? (true as const) : undefined,
              "aria-describedby": failures.length
                ? `${id}-${name}-error`
                : undefined,
            };
            const select =
              Array.isArray(control.enum) || control.type === "boolean";
            return (
              <div
                key={name}
                className="space-y-2 rounded border border-line p-3"
              >
                <label className="flex items-center gap-2 text-xs text-ink-3">
                  <input
                    type="checkbox"
                    aria-label={`Edit ${name}`}
                    checked={Boolean(edit)}
                    onChange={(event) => {
                      let text = "";
                      const stored =
                        current?.[name] !== undefined
                          ? current[name]
                          : asSchema(current?.metadata)[name];
                      const saved = editableValue(stored, field);
                      if (saved !== undefined && saved !== null) {
                        try {
                          validateValue(saved, field, name);
                          text =
                            control.type === "string" &&
                            !Array.isArray(control.enum)
                              ? String(saved)
                              : JSON.stringify(saved);
                        } catch {
                          /* Invalid saved data is never copied into the draft. */
                        }
                      }
                      change(
                        name,
                        event.target.checked
                          ? { text, clear: false }
                          : undefined,
                      );
                    }}
                  />
                  Edit {name}
                </label>
                {typeof field.description === "string" && (
                  <p className="text-xs text-ink-4">{field.description}</p>
                )}
                {edit && (
                  <>
                    {allowsNull(field) && (
                      <label className="flex items-center gap-2 text-xs text-ink-4">
                        <input
                          type="checkbox"
                          aria-label={`Clear ${name}`}
                          checked={edit.clear}
                          onChange={(event) =>
                            change(name, {
                              ...edit,
                              clear: event.target.checked,
                            })
                          }
                        />
                        Clear {name}
                      </label>
                    )}
                    {select ? (
                      <select
                        {...accessibility}
                        aria-label={name}
                        className={inputClass}
                        disabled={edit.clear}
                        value={edit.text}
                        onChange={(event) =>
                          change(name, { ...edit, text: event.target.value })
                        }
                      >
                        <option value="">Choose a value</option>
                        {(Array.isArray(control.enum)
                          ? control.enum
                          : [true, false]
                        )
                          .filter((value) => value !== null)
                          .map((value) => (
                            <option
                              key={JSON.stringify(value)}
                              value={JSON.stringify(value)}
                            >
                              {String(value)}
                            </option>
                          ))}
                      </select>
                    ) : ["string", "number", "integer"].includes(
                        String(control.type),
                      ) ? (
                      <input
                        {...accessibility}
                        aria-label={name}
                        disabled={edit.clear}
                        type={control.type === "string" ? "text" : "number"}
                        step={control.type === "integer" ? "1" : "any"}
                        className={inputClass}
                        value={edit.text}
                        onChange={(event) =>
                          change(name, { ...edit, text: event.target.value })
                        }
                      />
                    ) : (
                      <textarea
                        {...accessibility}
                        aria-label={name}
                        disabled={edit.clear}
                        className={`${inputClass} font-mono`}
                        rows={4}
                        value={edit.text}
                        placeholder="JSON value"
                        onChange={(event) =>
                          change(name, { ...edit, text: event.target.value })
                        }
                      />
                    )}
                  </>
                )}
                {failures.length > 0 && (
                  <p
                    id={`${id}-${name}-error`}
                    role="alert"
                    className="text-xs text-danger"
                  >
                    {failures
                      .map(
                        (failure) =>
                          `${failure.loc.slice(2).join(".")}: ${failure.msg}`,
                      )
                      .join("; ")}
                  </p>
                )}
              </div>
            );
          })}
          {schema && !fields.length && (
            <p className="text-xs text-ink-4">
              No additional settings advertised.
            </p>
          )}
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
        </div>
      )}
    </details>
  );
});
export default AdvancedPolicySettings;
