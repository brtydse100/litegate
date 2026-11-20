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
        // White text on navy and solid button fills.
        paper: "#FFFFFF",
        canvas: token("canvas"),
        card: token("card"),
        well: token("well"),
        line: {
          DEFAULT: token("line"),
          soft: token("line-soft"),
          input: token("line-input"),
        },
        navy: {
          DEFAULT: token("navy"),
          2: token("navy-2"),
          3: token("navy-3"),
          text: token("navy-text"),
          ink: token("navy-ink"),
          muted: token("navy-muted"),
        },
        ice: token("ice"),
        blue: hue("blue"),
        teal: solidHue("teal"),
        cyan: hue("cyan"),
        periwinkle: hue("periwinkle"),
        mint: hue("mint"),
        sand: solidHue("sand"),
        danger: {
          DEFAULT: token("danger"),
          line: token("danger-line"),
          tint: token("danger-tint"),
          solid: token("danger-solid"),
        },
        ready: token("ready"),
        alert: token("alert"),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "ui-sans-serif", "sans-serif"],
        mono: [
          '"IBM Plex Mono"',
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
