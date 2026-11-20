import type { ReactNode } from "react";
import { toneDot, toneSurface, usageTone, type Tone } from "./ui";

/** Page title, one-line description and optional actions on the right. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3.5">
      <div className="min-w-0">
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-4">
            {eyebrow}
          </p>
        )}
        <h1 className="mt-0.5 text-[28px] font-bold tracking-[-0.01em] text-ink">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-3xl text-[15px] text-ink-3">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Pill({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold ${toneSurface[tone]}`}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${toneDot[tone]}`}
      />
      {children}
    </span>
  );
}

export function Callout({
  tone = "info",
  title,
  children,
  role,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <div
      role={role}
      className={`rounded-xl border px-4 py-3 text-sm leading-relaxed ${toneSurface[tone]}`}
    >
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
    </div>
  );
}

/** Thin spend bar; colour follows how much of the budget is used. */
export function UsageBar({
  percent,
  className = "",
}: {
  percent: number;
  className?: string;
}) {
  return (
    <span className={`block h-[5px] rounded-[3px] bg-line-soft ${className}`}>
      <span
        className={`block h-[5px] rounded-[3px] ${usageTone(percent)}`}
        style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
      />
    </span>
  );
}

/** Metric card with a coloured top edge, as on the Organization page. */
export function MetricCard({
  accent,
  caption,
  value,
  sub,
  children,
}: {
  accent: string;
  caption: string;
  value: ReactNode;
  sub?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div
      className={`flex flex-col gap-1 rounded-[10px] border border-t-[3px] border-line bg-card px-[18px] pb-[18px] pt-4 ${accent}`}
    >
      <span className="text-xs font-semibold uppercase tracking-[0.04em] text-ink-4">
        {caption}
      </span>
      <span className="inline-flex items-center gap-2.5 text-[26px] font-semibold text-ink">
        {value}
      </span>
      {sub && <span className="text-[13px] text-ink-3">{sub}</span>}
      {children}
    </div>
  );
}
