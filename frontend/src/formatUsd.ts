/** Keep small usage charges visible without rounding nonzero values to zero. */
export function formatUsd(value: number): string {
  if (value !== 0 && Math.abs(value) < 0.0000000001)
    return `$${value.toExponential(3)}`;
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: 6,
    maximumFractionDigits: 10,
  })}`;
}
