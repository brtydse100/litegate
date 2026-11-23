/** Shared class names so every page uses the same controls and surfaces. */

const button =
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-[background-color,filter,opacity] duration-150 active:brightness-95 disabled:cursor-not-allowed disabled:opacity-40";

// Apple's button styles: filled for the main action, grey for the rest,
// plain accent text for low-emphasis actions.
export const buttonPrimary = `${button} bg-blue-solid text-paper hover:brightness-110`;
export const buttonCreate = buttonPrimary;
export const buttonDanger = `${button} bg-danger-solid text-paper hover:brightness-110`;
export const buttonSecondary = `${button} bg-ink/[0.06] text-ink hover:bg-ink/10`;
export const buttonGhost = `${button} text-blue-ink hover:bg-blue-tint`;
// Colours live only in the variants: Tailwind resolves two colour classes on
// one element by stylesheet order, not by their order in the class string.
const small =
  "inline-flex min-h-8 items-center justify-center gap-1.5 rounded-md px-3 text-[13px] font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40";
export const buttonSmall = `${small} bg-ink/[0.06] text-ink hover:bg-ink/10`;
export const buttonSmallDanger = `${small} bg-danger-tint text-danger hover:brightness-95`;

export const fieldInput =
  "min-h-10 w-full rounded-lg border border-line-input bg-card px-3 text-sm text-ink transition-shadow duration-150 placeholder:text-ink-4 focus:border-blue focus:outline-none focus:ring-[3px] focus:ring-blue/25 disabled:opacity-60";
export const fieldLabel =
  "flex flex-col gap-1.5 text-[13px] font-medium text-ink-2";

/** Grouped section: a white rounded block on the grey page, as in Settings. */
export const card = "rounded-xl border border-line-soft bg-card";
export const cardHeader =
  "flex flex-wrap items-center justify-between gap-3 border-b border-line-soft px-5 py-3";
export const cardTitle = "text-[15px] font-semibold text-ink";

/** Column captions above a list or table. */
export const tableHead =
  "border-b border-line-soft text-xs font-medium text-ink-4";
export const tableRow = "border-b border-line-soft last:border-b-0";

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral";

export const toneText: Record<Tone, string> = {
  ok: "text-green-ink",
  warn: "text-orange-ink",
  bad: "text-danger",
  info: "text-blue-ink",
  neutral: "text-ink-3",
};
export const toneSurface: Record<Tone, string> = {
  ok: "border-transparent bg-green-tint text-green-ink",
  warn: "border-transparent bg-orange-tint text-orange-ink",
  bad: "border-transparent bg-danger-tint text-danger",
  info: "border-transparent bg-blue-tint text-blue-ink",
  neutral: "border-transparent bg-well text-ink-3",
};
export const toneDot: Record<Tone, string> = {
  ok: "bg-green",
  warn: "bg-orange",
  bad: "bg-danger",
  info: "bg-blue",
  neutral: "bg-ink-5",
};

/** Spend bar colour: blue, then orange at 80%, red at 95%. */
export function usageTone(percent: number): string {
  return percent >= 95 ? "bg-danger" : percent >= 80 ? "bg-orange" : "bg-blue";
}
