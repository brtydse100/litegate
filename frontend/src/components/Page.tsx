import type { ReactNode } from "react";
import { toneDot, toneSurface, usageTone, type Tone } from "./ui";

/** Large page title, one-line description and optional actions. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3.5">
      <div className="min-w-0">
        <h1 className="text-[28px] font-bold leading-tight tracking-[-0.02em] text-ink">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-3xl text-[15px] leading-snug text-ink-4">
            {description}
          </p>
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
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${toneSurface[tone]}`}
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
    <span className={`block h-1.5 rounded-full bg-well ${className}`}>
      <span
        className={`block h-1.5 rounded-full transition-[width] duration-300 ${usageTone(percent)}`}
        style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
      />
    </span>
  );
}
