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
        surface: {
          0: "#0F1117",
          1: "#1A1D27",
          2: "#22263A",
          3: "#2A2E42",
        },
        accent: {
          DEFAULT: "#3F6AB0",
          hover: "#345A97",
          muted: "#243F6B",
        },
        // Legacy components use indigo utilities; map them onto the new blue.
        indigo: {
          50: "#EEF3FA",
          100: "#E0E9F6",
          200: "#C3D3EC",
          300: "#9AB4DD",
          400: "#6F91C9",
          500: "#4F78BB",
          600: "#3F6AB0",
          700: "#345A97",
          800: "#2B4E86",
          900: "#243F6B",
          950: "#18294A",
        },
        ink: {
          DEFAULT: token("ink"),
          2: token("ink-2"),
          3: token("ink-3"),
          4: token("ink-4"),
          5: token("ink-5"),
        },
        // White text for navy and blue surfaces; legacy CSS remaps `text-white`.
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
