import { expect, it } from "vitest";
import { formatUsd } from "./formatUsd";

it.each([
  [0, "$0.00"],
  [0.0000000123, "$0.00"],
  [0.004, "$0.00"],
  [0.01, "$0.01"],
  [12.345678, "$12.35"],
  [1234.5, "$1,234.50"],
  [-1.235, "-$1.24"],
])("formats %s with exactly two fractional digits", (amount, expected) => {
  expect(formatUsd(Number(amount))).toBe(expected);
});
