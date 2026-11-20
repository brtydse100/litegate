import { describe, expect, it } from "vitest";
import * as ui from "./ui";

// Two colour classes of the same kind on one element resolve by stylesheet
// order, so a shared class string must never carry competing colours.
const colour =
  /^(text|bg|border)-(ink|paper|blue|teal|sand|danger|mint|cyan|card|canvas|well|line|navy|periwinkle)\b/;

describe("shared class strings", () => {
  const strings: [string, string][] = [];
  for (const [name, value] of Object.entries(ui) as [string, unknown][])
    if (typeof value === "string") strings.push([name, value]);

  it.each(strings)("%s has one colour per property", (_name, classes) => {
    const kinds = classes
      .split(/\s+/)
      .filter((name: string) => colour.test(name))
      .map((name: string) => name.split("-")[0]);
    expect(new Set(kinds).size).toBe(kinds.length);
  });
});

describe("uses of shared buttons", () => {
  const sources = import.meta.glob("../**/*.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  it("never add colours on top of a shared button's own", () => {
    const offenders = Object.entries(sources).flatMap(([file, text]) =>
      [...text.matchAll(/\$\{button\w*\}([^`]*)`/g)]
        .filter(([, extra]) =>
          extra
            .replace(/["'{}]/g, " ")
            .split(/\s+/)
            .map((name) => name.replace(/^([a-z-]+:)+/, ""))
            .some((name) => colour.test(name)),
        )
        .map(([match]) => `${file}: ${match}`),
    );
    expect(offenders).toEqual([]);
  });
});
