import type { Config } from "tailwindcss";

/** Colour channels live in index.css so light and dark themes share class names. */
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const hue = (name: string) => ({
  DEFAULT: token(name),
  tint: token(`${name}-tint`),
  ink: token(`${name}-ink`),
});

/** A hue that also fills solid buttons with white text. */
const solidHue = (name: string) => ({
  ...hue(name),
  solid: token(`${name}-solid`),
});

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: token("ink"),
          2: token("ink-2"),
          3: token("ink-3"),
          4: token("ink-4"),
          5: token("ink-5"),
        },
        // White text on solid fills.
        paper: "#FFFFFF",
        canvas: token("canvas"),
        card: token("card"),
        well: token("well"),
        sidebar: token("sidebar"),
        segment: token("segment"),
        line: {
          DEFAULT: token("line"),
          soft: token("line-soft"),
          input: token("line-input"),
        },
        blue: solidHue("blue"),
        teal: hue("teal"),
        cyan: hue("cyan"),
        indigo: hue("indigo"),
        green: hue("green"),
        orange: solidHue("orange"),
        danger: {
          DEFAULT: token("danger"),
          line: token("danger-line"),
          tint: token("danger-tint"),
          solid: token("danger-solid"),
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Text"',
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          '"SF Mono"',
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
