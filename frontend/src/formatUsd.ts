/** Round currency for display only; retain full precision in data and edits. */
export function formatUsd(value: number): string {
  return `${value < 0 ? "-" : ""}$${Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
