import type { Config } from "tailwindcss";

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
          DEFAULT: "#6366F1",
          hover: "#4F46E5",
          muted: "#312E81",
        },
      },
      fontFamily: {
        sans: ["system-ui", "ui-sans-serif", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;