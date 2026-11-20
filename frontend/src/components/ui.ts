/** Shared class names so every page uses the same controls and surfaces. */

const button =
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50";

export const buttonPrimary = `${button} bg-blue text-paper hover:brightness-90`;
export const buttonCreate = `${button} bg-teal-solid text-paper hover:brightness-90`;
export const buttonDanger = `${button} bg-danger-solid text-paper hover:brightness-90`;
export const buttonSecondary = `${button} border border-line-input bg-card font-medium text-ink-2 hover:bg-canvas`;
export const buttonGhost = `${button} font-medium text-ink-3 hover:bg-well hover:text-ink`;
// Colours live only in the variants: Tailwind resolves two colour classes on
// one element by stylesheet order, not by their order in the class string.
const small =
  "inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg border bg-card px-3 text-[13px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
export const buttonSmall = `${small} border-line-input text-ink-2 hover:bg-canvas`;
export const buttonSmallDanger = `${small} border-danger-line text-danger hover:bg-danger-tint`;

export const fieldInput =
  "min-h-11 w-full rounded-lg border border-line-input bg-card px-3 text-sm text-ink placeholder:text-ink-4 focus:border-blue focus:outline-none focus:ring-2 focus:ring-blue/20 disabled:opacity-60";
export const fieldLabel =
  "flex flex-col gap-1.5 text-[13px] font-semibold text-ink-2";

export const card = "rounded-xl border border-line bg-card";
export const cardHeader =
  "flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5";
export const cardTitle = "text-base font-bold text-ink";

/** Column captions above a list or table. */
export const tableHead =
  "border-b border-line-soft bg-canvas text-xs font-semibold uppercase tracking-[0.04em] text-ink-4";
export const tableRow = "border-b border-line-soft last:border-b-0";

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral";

export const toneText: Record<Tone, string> = {
  ok: "text-mint-ink",
  warn: "text-sand-ink",
  bad: "text-danger",
  info: "text-blue-ink",
  neutral: "text-ink-3",
};
export const toneSurface: Record<Tone, string> = {
  ok: "border-mint/40 bg-mint-tint text-mint-ink",
  warn: "border-sand/40 bg-sand-tint text-sand-ink",
  bad: "border-danger-line bg-danger-tint text-danger",
  info: "border-blue/30 bg-blue-tint text-blue-ink",
  neutral: "border-line bg-canvas text-ink-3",
};
export const toneDot: Record<Tone, string> = {
  ok: "bg-mint",
  warn: "bg-sand",
  bad: "bg-danger",
  info: "bg-blue",
  neutral: "bg-ink-5",
};

/** Spend bar colour: blue, then sand at 80%, red at 95%. */
export function usageTone(percent: number): string {
  return percent >= 95 ? "bg-danger" : percent >= 80 ? "bg-sand" : "bg-blue";
}
