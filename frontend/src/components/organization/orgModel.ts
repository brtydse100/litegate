import { formatUsd } from "../../formatUsd";
import type {
  OrganizationGroup,
  OrganizationNode,
} from "../../types/organization";

export interface Hue {
  name: string;
  bar: string;
  tint: string;
  ink: string;
  color: string;
}

/** Group colours cycle blue → periwinkle → teal → cyan → mint → navy. */
export const palette: Hue[] = [
  {
    name: "blue",
    bar: "bg-blue",
    tint: "bg-blue-tint",
    ink: "text-blue-ink",
    color: "rgb(var(--blue))",
  },
  {
    name: "periwinkle",
    bar: "bg-periwinkle",
    tint: "bg-periwinkle-tint",
    ink: "text-periwinkle-ink",
    color: "rgb(var(--periwinkle))",
  },
  {
    name: "teal",
    bar: "bg-teal",
    tint: "bg-teal-tint",
    ink: "text-teal-ink",
    color: "rgb(var(--teal))",
  },
  {
    name: "cyan",
    bar: "bg-cyan",
    tint: "bg-cyan-tint",
    ink: "text-cyan-ink",
    color: "rgb(var(--cyan))",
  },
  {
    name: "mint",
    bar: "bg-mint",
    tint: "bg-mint-tint",
    ink: "text-mint-ink",
    color: "rgb(var(--mint))",
  },
  {
    name: "navy",
    bar: "bg-navy",
    tint: "bg-well",
    ink: "text-ink-2",
    color: "rgb(var(--navy))",
  },
];

export type Group = OrganizationNode &
  Partial<Pick<OrganizationGroup, "group_spend" | "sync_error">>;

export function groupInitials(name: string) {
  const words = name.split(/[\s_-]+/).filter(Boolean);
  if (words.length > 1) return (words[0][0] + words[1][0]).toUpperCase();
  const match = name.match(/^([a-z]+)(\d+)$/i);
  if (match) return (match[1][0] + match[2][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

/**
 * Colour of a group: each direct child of the selected root gets the next
 * palette colour in configuration order, and its descendants share it.
 */
export function hueFor(
  group: Pick<Group, "id" | "parent_id">,
  rootId: string | null,
  byId: Map<string, Pick<Group, "id" | "parent_id">>,
  siblings: string[],
): Hue {
  let branch = group;
  while (branch.parent_id && branch.parent_id !== rootId) {
    const parent = byId.get(branch.parent_id);
    if (!parent) break;
    branch = parent;
  }
  const index = siblings.indexOf(branch.id);
  return palette[(index < 0 ? 0 : index) % palette.length];
}

export const percent = (
  spend: number | null | undefined,
  total: number | null,
) => (spend == null || !total ? null : Math.round((spend / total) * 100));

export const money = (value: number | null | undefined) =>
  value == null ? "—" : formatUsd(value);

/** Whole-dollar amounts drop their cents to keep dense tables readable. */
export const shortMoney = (value: number | null | undefined) =>
  value == null
    ? "—"
    : Number.isInteger(value)
      ? `$${value.toLocaleString()}`
      : formatUsd(value);

export function pluralWord(word: string) {
  const lower = word.toLowerCase();
  if (lower === "person") return "people";
  return lower.endsWith("s") ? lower : `${lower}s`;
}

export function plural(count: number, word: string) {
  return `${count} ${count === 1 ? word.toLowerCase() : pluralWord(word)}`;
}
