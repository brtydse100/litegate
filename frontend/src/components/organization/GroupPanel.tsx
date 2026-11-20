import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "../../api/client";
import DismissibleMessage from "../DismissibleMessage";
import { durationLabel } from "../../keyBudget";
import type { BudgetGroup } from "../../types/budgets";
import {
  groupInitials,
  limitOrigin,
  money,
  percent,
  plural,
  pluralWord,
  shortMoney,
  type Group,
  type Hue,
} from "./orgModel";

const field =
  "min-h-11 rounded-lg border border-line-input bg-card px-3 text-sm font-normal text-ink";
const label = "flex flex-col gap-1.5 text-[13px] font-semibold text-ink-2";

interface Child {
  group: Group;
  hue: Hue;
}

/** Side panel for the selected group: usage, limits and its sub-groups. */
export default function GroupPanel({
  group,
  hue,
  parent,
  source,
  levelName,
  childLevelName,
  subGroups,
  totalSpend,
  ownSpend,
  ownSpendState,
  budgetGroup,
  revision,
  onClose,
  onSelect,
}: {
  group: Group;
  hue: Hue;
  parent?: Group;
  /** Group the per-person allowance is inherited from, if any. */
  source?: Group;
  levelName?: string;
  childLevelName?: string;
  subGroups: Child[];
  /** Spend including sub-groups, from the organization overview. */
  totalSpend: number | null | undefined;
  /** The group's own team spend, from the group detail. */
  ownSpend: number | null | undefined;
  ownSpendState: "loading" | "error" | "ready";
  budgetGroup?: BudgetGroup;
  revision?: number;
  onClose: () => void;
  onSelect: (id: string) => void;
}) {
  const client = useQueryClient();
  const heading = useRef<HTMLHeadingElement>(null);
  // Opening a group moves focus to its panel: beside the report from 1140px
  // (sidebar 236 + report 560 + panel 340), above it on narrower screens.
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const [envelope, setEnvelope] = useState<string | null>(null);
  const [perUser, setPerUser] = useState<string | null>(null);
  const editEnvelope = !!budgetGroup?.can_edit_envelope && revision != null;
  const editPerUser = !!budgetGroup?.can_edit_per_user;
  const save = useMutation({
    mutationFn: async () => {
      if (editEnvelope && envelope !== null) {
        const view = await api.setGroupBudget(group.id, revision!, envelope);
        client.setQueryData(["organization-budgets"], view);
        setEnvelope(null);
      }
      if (editPerUser && perUser !== null) {
        await api.setGroupPerUser(group.id, perUser === "" ? null : perUser);
        setPerUser(null);
      }
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["organization-budgets"] });
      void client.invalidateQueries({ queryKey: ["organization-overview"] });
      void client.invalidateQueries({ queryKey: ["organization-children"] });
      void client.invalidateQueries({ queryKey: ["teams"] });
    },
    // A conflict means the revision or allocations changed; reload them so
    // the retained draft can be reviewed and saved against current data.
    onError: () =>
      void client.invalidateQueries({ queryKey: ["organization-budgets"] }),
  });
  const dirty =
    (editEnvelope && envelope !== null) || (editPerUser && perUser !== null);
  const total = group.group_total;
  const used = percent(totalSpend, total);
  const childNames = subGroups.map((child) => child.group.name);
  const inheritedFrom = source;
  const segments = [
    ...(ownSpend != null && ownSpend > 0
      ? [{ name: "own", value: ownSpend, color: "rgb(var(--ink-3))" }]
      : []),
    ...subGroups
      .filter((child) => (child.group.group_spend ?? 0) > 0)
      .map((child) => ({
        name: child.group.name,
        value: child.group.group_spend ?? 0,
        color: child.hue.color,
      })),
  ];
  const scale = Math.max(total ?? 0, totalSpend ?? 0) || 1;

  return (
    <aside
      data-group-panel
      aria-label={`Edit ${group.name}`}
      className="flex basis-full flex-col gap-[18px] border-b border-line bg-card p-6 min-[1140px]:w-[340px] min-[1140px]:shrink-0 min-[1140px]:basis-auto min-[1140px]:sticky min-[1140px]:top-0 min-[1140px]:order-last min-[1140px]:max-h-screen min-[1140px]:overflow-y-auto min-[1140px]:border-b-0 min-[1140px]:border-l"
    >
      <div className="flex flex-col gap-2.5">
        <nav aria-label="Group path" className="text-xs text-ink-4">
          {group.path.slice(0, -1).map((name, index) => (
            <span key={index}>
              {name} <span aria-hidden="true">›</span>{" "}
            </span>
          ))}
          <strong className="text-ink-2">{group.name}</strong>
        </nav>
        <div className="flex items-start justify-between gap-2.5">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className={`inline-flex h-10 w-10 items-center justify-center rounded-[10px] font-bold ${hue.tint} ${hue.ink}`}
            >
              {groupInitials(group.name)}
            </span>
            <div>
              <h2
                ref={heading}
                tabIndex={-1}
                className="text-lg font-bold text-ink outline-none"
              >
                {group.name}
              </h2>
              <p className="mt-0.5 text-[13px] text-ink-4">
                {[
                  levelName,
                  subGroups.length && childLevelName
                    ? plural(subGroups.length, childLevelName)
                    : null,
                  plural(group.members, "person"),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-4 hover:bg-canvas"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2.5 rounded-[10px] border border-line p-3.5">
        <span className="flex justify-between gap-3 text-[13px]">
          <span className="text-ink-2">
            {totalSpend === undefined
              ? "Loading spend…"
              : total == null
                ? `${money(totalSpend)} spent`
                : `${money(totalSpend)} of ${shortMoney(total)}`}
            {subGroups.length > 0 && childLevelName
              ? ` · incl. ${pluralWord(childLevelName)}`
              : ""}
          </span>
          {used != null && (
            <span
              className={`font-semibold ${used >= 80 ? "text-sand-ink" : "text-blue-ink"}`}
            >
              {used}%
            </span>
          )}
        </span>
        <span
          role="img"
          aria-label={`Spend split for ${group.name}`}
          className="flex h-2 gap-0.5 overflow-hidden rounded bg-line-soft"
        >
          {segments.map((segment) => (
            <span
              key={segment.name}
              style={{
                width: `${(segment.value / scale) * 100}%`,
                background: segment.color,
              }}
            />
          ))}
        </span>
        <span className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-3">
          {ownSpendState === "ready" ? (
            <span>
              <span style={{ color: "rgb(var(--ink-3))" }}>■</span> own{" "}
              {shortMoney(ownSpend)}
            </span>
          ) : ownSpendState === "loading" ? (
            <span>Loading team details...</span>
          ) : (
            <span>Own spend unavailable</span>
          )}
          {subGroups.map((child) => (
            <span key={child.group.id}>
              <span style={{ color: child.hue.color }}>■</span>{" "}
              {child.group.name} {shortMoney(child.group.group_spend)}
            </span>
          ))}
        </span>
      </div>

      {editEnvelope ? (
        <label className={label}>
          Group budget
          <span className="flex min-h-11 items-center rounded-lg border border-line-input px-3">
            <span className="text-ink-4">$</span>
            <input
              type="number"
              min="0"
              step="0.01"
              aria-label={`${group.name} group budget`}
              value={envelope ?? String(budgetGroup!.assigned)}
              onChange={(event) => setEnvelope(event.target.value)}
              className="flex-1 border-0 bg-transparent px-1.5 py-2.5 text-sm font-normal text-ink outline-none"
            />
          </span>
        </label>
      ) : (
        <div className={label}>
          Group budget
          <span className="text-sm font-normal text-ink-3">
            {budgetGroup
              ? shortMoney(budgetGroup.assigned)
              : total == null
                ? "No target"
                : shortMoney(total)}
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className={label}>
          Resets every
          <span className="text-sm font-normal text-ink-3">
            {durationLabel(group.duration) ?? "No automatic reset"}
          </span>
        </div>
        {editPerUser ? (
          <label className={label}>
            Per-person limit
            <input
              type="number"
              min="0"
              step="0.000001"
              aria-label={`${group.name} per-person limit`}
              placeholder={
                budgetGroup!.per_user_override != null
                  ? "Inherited or configured"
                  : "No limit"
              }
              value={
                perUser ??
                (budgetGroup!.per_user == null
                  ? ""
                  : String(budgetGroup!.per_user))
              }
              onChange={(event) => setPerUser(event.target.value)}
              className={field}
            />
          </label>
        ) : (
          <div className={label}>
            Per-person limit
            <span className="text-sm font-normal text-ink-3">
              {group.per_user == null ? "No limit" : shortMoney(group.per_user)}
            </span>
          </div>
        )}
        {editPerUser && budgetGroup!.per_user_override != null && (
          <p className="col-span-2 -mt-1 text-xs text-ink-4">
            Set here; leave empty and save to return to the inherited or
            configured limit.
          </p>
        )}
        <p className="col-span-2 -mt-1 text-xs text-ink-4">
          {limitOrigin(group, parent, inheritedFrom).description}
          {childLevelName && subGroups.length
            ? ` · ${pluralWord(childLevelName)} can override`
            : ""}
        </p>
      </div>

      {subGroups.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold text-ink-2">
            {childLevelName
              ? pluralWord(childLevelName).replace(/^./, (c) => c.toUpperCase())
              : "Sub-groups"}
          </span>
          <span className="flex flex-wrap gap-x-1 text-[13px] text-ink-3">
            {childNames.map((name, index) => (
              <button
                key={subGroups[index].group.id}
                type="button"
                onClick={() => onSelect(subGroups[index].group.id)}
                className="text-blue-ink hover:underline"
              >
                {name}
                {index < childNames.length - 1 ? "," : ""}
              </button>
            ))}
          </span>
        </div>
      )}

      {group.sync_error && (
        <p role="alert" className="text-sm text-sand-ink">
          {group.sync_error}
        </p>
      )}
      {save.error && (
        <DismissibleMessage
          role="alert"
          messageKey={save.error.message}
          className="text-sm text-danger"
        >
          {save.error.message}
        </DismissibleMessage>
      )}

      {(editEnvelope || editPerUser) && (
        <div className="mt-auto flex gap-2 border-t border-line-soft pt-3">
          <button
            type="button"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
            className="min-h-11 flex-1 rounded-lg bg-navy px-4 font-semibold text-paper hover:bg-navy-2 disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save changes"}
          </button>
          <button
            type="button"
            disabled={save.isPending}
            onClick={() => {
              setEnvelope(null);
              setPerUser(null);
              save.reset();
            }}
            className="min-h-11 rounded-lg border border-line-input bg-card px-4 text-ink-2 hover:bg-canvas"
          >
            Cancel
          </button>
        </div>
      )}
    </aside>
  );
}
