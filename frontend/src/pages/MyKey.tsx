import { useState, type ReactNode } from "react";
import { KeyRound, Plus, RefreshCw, RotateCcw } from "lucide-react";
import PersonalKeySecret from "../components/PersonalKeySecret";
import DismissibleMessage from "../components/DismissibleMessage";
import { keyToken } from "../components/BulkKeyEditor";
import { formatUsd } from "../formatUsd";
import {
  allowedModels,
  budgetSummary,
  parseLiteLLMDate,
  type BudgetSummary,
} from "../keyBudget";
import type { KeyInfo } from "../types";

export function keyAccessStatus(key: KeyInfo) {
  if (key.blocked) return "Blocked";
  if (key.expires && parseLiteLLMDate(key.expires).getTime() <= Date.now())
    return "Expired";
  if (key.policy_error) return "Needs attention";
  if (key.user_budget_available === false)
    return key.policy_notice ? "Updating" : "Budget details unavailable";
  if (
    (key.max_budget != null && key.spend >= key.max_budget) ||
    (key.user_budget != null &&
      key.user_spend != null &&
      key.user_spend >= key.user_budget)
  )
    return "Budget reached";
  return "Ready";
}

const shortDate = (date: Date) =>
  date.toLocaleDateString(undefined, { month: "short", day: "numeric" });

const card = "rounded-2xl border border-line bg-card";

/** LiteLLM's masked `key_name` (e.g. `sk-...7f3a`) with a longer mask. */
export function maskedKey(key: KeyInfo) {
  const name = key.key_name?.trim();
  const match = name?.match(/^(.*?)\.{3,}(.+)$/);
  if (match) return `${match[1]}••••••••••••••••${match[2]}`;
  return "sk-••••••••••••••••";
}

function BudgetRing({ summary }: { summary: BudgetSummary }) {
  const radius = 86;
  const circumference = 2 * Math.PI * radius;
  const remaining = summary.remaining ?? 0;
  const color =
    remaining <= 0.1
      ? "rgb(var(--danger))"
      : remaining <= 0.25
        ? "rgb(var(--sand))"
        : "rgb(var(--teal))";
  const percent = Math.round(remaining * 100);
  return (
    <div className="relative h-[200px] w-[200px]">
      <svg
        width="200"
        height="200"
        viewBox="0 0 200 200"
        role="img"
        aria-label={
          summary.available && summary.budget != null
            ? `${percent}% of budget remaining`
            : "Budget unavailable"
        }
      >
        <circle
          cx="100"
          cy="100"
          r={radius}
          fill="none"
          stroke="rgb(var(--line))"
          strokeWidth="12"
        />
        {summary.available && summary.budget != null && remaining > 0 && (
          <circle
            cx="100"
            cy="100"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${remaining * circumference} ${circumference}`}
            transform="rotate(-90 100 100)"
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5">
        {summary.available ? (
          <>
            <span className="text-[13px] text-ink-4">left to spend</span>
            <span className="text-[38px] font-semibold tracking-[-0.02em] text-ink">
              {formatUsd(summary.left ?? 0)}
            </span>
            <span className="text-[13px] text-ink-4">
              of {formatUsd(summary.budget ?? 0)}
            </span>
          </>
        ) : (
          <>
            <span className="text-[13px] text-ink-4">budget</span>
            <span className="text-2xl font-semibold text-ink">Unavailable</span>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div>
      <p className="mb-0.5 text-lg font-semibold text-ink">{value}</p>
      {label}
    </div>
  );
}

export function BudgetCard({ keyInfo }: { keyInfo: KeyInfo }) {
  const summary = budgetSummary(keyInfo);
  const unlimited = summary.available && summary.budget == null;
  const refill =
    summary.budget != null && summary.periodLabel
      ? summary.resetAt && summary.daysUntilReset != null
        ? `Refills to ${formatUsd(summary.budget)} in ${summary.daysUntilReset} day${
            summary.daysUntilReset === 1 ? "" : "s"
          } · ${shortDate(summary.resetAt)}`
        : `Refills to ${formatUsd(summary.budget)} every ${summary.periodLabel}`
      : null;
  return (
    <section
      aria-label="Budget"
      className={`${card} flex flex-col items-center gap-[18px] px-7 pb-7 pt-9`}
    >
      {unlimited ? (
        <div className="flex flex-col items-center gap-1 py-6 text-center">
          <span className="text-[13px] text-ink-4">spent so far</span>
          <span className="text-[38px] font-semibold tracking-[-0.02em] text-ink">
            {formatUsd(summary.spent)}
          </span>
          <span className="text-[13px] text-ink-4">No budget limit</span>
        </div>
      ) : (
        <BudgetRing summary={summary} />
      )}
      {refill && summary.available && (
        <p className="inline-flex items-center gap-2 rounded-full bg-teal-tint px-4 py-[7px] text-sm font-semibold text-teal-ink">
          <RotateCcw size={15} aria-hidden="true" />
          {refill}
        </p>
      )}
      <div className="grid w-full max-w-[480px] grid-cols-3 text-center text-[13px] text-ink-4">
        <Stat
          value={summary.available ? formatUsd(summary.spent) : "Unavailable"}
          label="spent"
        />
        <Stat
          value={
            summary.available && summary.perDay != null
              ? `~${formatUsd(summary.perDay)}`
              : "—"
          }
          label="per day"
        />
        <Stat
          value={
            !summary.available || summary.onTrack == null ? (
              "—"
            ) : summary.onTrack ? (
              "On track"
            ) : (
              <span className="text-sand-ink">Over pace</span>
            )
          }
          label="at this pace"
        />
      </div>
    </section>
  );
}

const bigButton =
  "flex min-h-[58px] w-full items-center justify-center gap-3 rounded-xl bg-blue px-6 py-4 text-[17px] font-semibold text-paper shadow-[0_1px_2px_rgba(22,27,34,0.12)] hover:brightness-90 disabled:opacity-50";

export function KeyCard({
  keyInfo,
  initialSecret,
  canReveal,
  onHide,
  action,
}: {
  keyInfo: KeyInfo;
  initialSecret?: string | null;
  canReveal: boolean;
  onHide: () => void;
  /** Regenerate button or its confirmation, supplied by the page. */
  action?: ReactNode;
}) {
  return (
    <section aria-label="Key" className={`${card} flex flex-col gap-4 p-6`}>
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.05em] text-ink-4">
        Your API key
        {keyInfo.key_alias && (
          <span className="ml-2 font-mono font-normal normal-case tracking-normal">
            {keyInfo.key_alias}
          </span>
        )}
      </h2>
      <PersonalKeySecret
        identifier={keyToken(keyInfo)}
        canReveal={canReveal}
        initialSecret={initialSecret}
        onHide={onHide}
        preview={maskedKey(keyInfo)}
      />
      {action}
      {keyInfo.policy_error && (
        <DismissibleMessage
          role="alert"
          messageKey={keyInfo.policy_error}
          className="rounded-lg border border-sand/40 bg-sand-tint px-4 py-3 text-sm text-sand-ink"
        >
          {keyInfo.policy_error}
        </DismissibleMessage>
      )}
      {keyInfo.policy_notice && (
        <DismissibleMessage
          messageKey={keyInfo.policy_notice}
          className="rounded-lg border border-cyan/30 bg-cyan-tint px-4 py-3 text-sm text-cyan-ink"
        >
          {keyInfo.policy_notice}
        </DismissibleMessage>
      )}
    </section>
  );
}

export function RegenerateButton({
  paused,
  onClick,
}: {
  paused: boolean;
  onClick: () => void;
}) {
  return (
    <>
      <button
        type="button"
        onClick={onClick}
        disabled={paused}
        className={bigButton}
      >
        <RefreshCw size={20} strokeWidth={2.2} aria-hidden="true" />
        {paused ? "Regeneration paused" : "Regenerate key"}
      </button>
      <p className="-mt-1 text-center text-[13px] text-ink-4">
        Lost it or think it leaked? Your spend and refill date stay the same.
      </p>
    </>
  );
}

export function RegenerateConfirm({
  pending,
  paused,
  onConfirm,
  onCancel,
}: {
  pending: boolean;
  paused: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      role="group"
      aria-label="Confirm key replacement"
      className="rounded-xl border border-sand/40 bg-sand-tint p-5"
    >
      <p className="text-sm font-semibold text-ink">Replace the current key?</p>
      <p className="mt-1 text-sm text-ink-3">
        The old key stops working immediately. Replacing it can take about 15
        seconds while its usage is carried over.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={pending || paused}
          className="min-h-11 rounded-lg bg-blue px-4 text-sm font-semibold text-paper hover:brightness-90 disabled:opacity-50"
        >
          {pending
            ? "Replacing..."
            : paused
              ? "Temporarily paused"
              : "Replace key"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="min-h-11 rounded-lg border border-line-input bg-card px-4 text-sm text-ink-2 hover:bg-canvas"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export function CreateKeyCard({
  pending,
  paused,
  onCreate,
}: {
  pending: boolean;
  paused: boolean;
  onCreate: () => void;
}) {
  return (
    <section
      aria-label="Create key"
      className="flex flex-col items-center gap-3.5 rounded-xl border border-blue/25 bg-card px-8 py-11 text-center"
    >
      <span
        aria-hidden="true"
        className="inline-flex h-14 w-14 items-center justify-center rounded-[14px] bg-blue-tint text-blue"
      >
        <KeyRound size={28} />
      </span>
      <h2 className="text-2xl font-bold text-ink">
        You don’t have an API key yet
      </h2>
      <p className="max-w-[460px] text-[15px] leading-normal text-ink-3">
        Create one to start sending requests through the gateway.
      </p>
      <button
        type="button"
        onClick={onCreate}
        disabled={pending || paused}
        className="mt-2 inline-flex min-h-[58px] items-center gap-2.5 rounded-xl bg-blue px-9 py-4 text-lg font-semibold text-paper shadow-[0_1px_2px_rgba(22,27,34,0.12)] hover:brightness-90 disabled:opacity-50"
      >
        <Plus size={20} strokeWidth={2.4} aria-hidden="true" />
        {pending
          ? "Creating..."
          : paused
            ? "Key actions paused"
            : "Create my API key"}
      </button>
      <p className="text-[13px] text-ink-4">
        The secret is shown once, so copy it straight away.
      </p>
    </section>
  );
}

const statusTone: Record<string, { label: string; dot: string }> = {
  Ready: { label: "Active", dot: "bg-ready" },
  "No key": { label: "No key yet", dot: "bg-navy-muted" },
  Blocked: { label: "Blocked", dot: "bg-danger" },
  Expired: { label: "Expired", dot: "bg-danger" },
  "Budget reached": { label: "Budget reached", dot: "bg-sand" },
};

export function StatusCard({
  keyInfo,
  status,
}: {
  keyInfo?: KeyInfo;
  status: string;
}) {
  const tone = statusTone[status] ?? { label: status, dot: "bg-sand" };
  const path = keyInfo?.organization_path?.filter(Boolean) ?? [];
  const team = path.length ? path[path.length - 1] : keyInfo?.team_id;
  const parents = path.slice(0, -1);
  const summary = keyInfo ? budgetSummary(keyInfo) : null;
  const used =
    summary?.available && summary.budget
      ? Math.min(100, Math.round((summary.spent / summary.budget) * 100))
      : null;
  return (
    <div className="flex flex-col gap-[18px] rounded-2xl bg-navy p-[22px] text-paper">
      <span className="flex items-center justify-between text-[13px] text-navy-text">
        <span>Status</span>
        <span className="inline-flex items-center gap-[7px] rounded-full bg-navy-2 px-3 py-1 font-semibold text-paper">
          <span className={`h-2 w-2 rounded-full ${tone.dot}`} />
          {tone.label}
        </span>
      </span>
      {team && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.05em] text-navy-muted">
            Team
          </p>
          <p className="mt-1 break-words text-[22px] font-semibold">{team}</p>
          {parents.length > 0 && (
            <p className="mt-0.5 text-[13px] text-navy-text">
              {parents.join(" › ")}
            </p>
          )}
        </div>
      )}
      {used != null && (
        <div className="flex flex-col gap-2">
          <span className="block h-1.5 rounded-[3px] bg-navy-3">
            <span
              className="block h-1.5 rounded-[3px] bg-ice"
              style={{ width: `${used}%` }}
            />
          </span>
          <span className="flex justify-between text-[13px] text-navy-text">
            <span>{used}% of budget used</span>
            {summary?.resetAt && <span>{shortDate(summary.resetAt)}</span>}
          </span>
        </div>
      )}
    </div>
  );
}

export function DetailsCard({ keys }: { keys: KeyInfo[] }) {
  const [expanded, setExpanded] = useState(false);
  const first = keys[0];
  const unrestricted = keys.some((key) => allowedModels(key.models) === null);
  const models = unrestricted
    ? null
    : (allowedModels(keys.flatMap((key) => key.models ?? [])) ?? []);
  const rows: Array<[string, ReactNode]> = [];
  if (first) {
    rows.push([
      "Models",
      models == null ? (
        "All models"
      ) : models.length <= 3 ? (
        models.join(", ")
      ) : (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="accessible-models"
          onClick={() => setExpanded((value) => !value)}
          className="text-right text-blue-ink underline-offset-2 hover:underline"
        >
          {models.length} models
        </button>
      ),
    ]);
    if (first.rpm_limit != null)
      rows.push(["Rate limit", `${first.rpm_limit.toLocaleString()} / min`]);
    if (first.expires)
      rows.push([
        "Expires",
        parseLiteLLMDate(first.expires).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
        }),
      ]);
  }
  if (!rows.length) return null;
  return (
    <div className="rounded-2xl border border-line bg-card px-5 py-1.5 text-sm">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3">
        {rows.map(([label, value], index) => (
          <div key={label} className="contents">
            <dt
              className={`py-3 text-ink-4 ${index < rows.length - 1 ? "border-b border-line-soft" : ""}`}
            >
              {label}
            </dt>
            <dd
              className={`py-3 text-right text-ink ${index < rows.length - 1 ? "border-b border-line-soft" : ""}`}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
      {expanded && models && (
        <ul
          id="accessible-models"
          aria-label="Accessible models"
          className="flex flex-wrap gap-1.5 border-t border-line-soft py-3"
        >
          {models.map((model) => (
            <li
              key={model}
              className="rounded-md bg-canvas px-2 py-1 font-mono text-xs text-ink-2"
            >
              {model}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function LinkCard({
  links,
}: {
  links: Array<{ href: string; label: string }>;
}) {
  if (!links.length) return null;
  return (
    <div className="flex flex-col rounded-2xl border border-line bg-card px-5 py-1.5 text-sm">
      {links.map((link, index) => (
        <a
          key={link.href}
          href={link.href}
          target="_blank"
          rel="noreferrer"
          className={`flex min-h-11 items-center justify-between py-2 font-medium text-blue-ink no-underline hover:underline ${
            index < links.length - 1 ? "border-b border-line-soft" : ""
          }`}
        >
          {link.label} <span aria-hidden="true">↗</span>
        </a>
      ))}
    </div>
  );
}
