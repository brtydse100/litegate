import { useState } from "react";
import { Moon, Sun } from "lucide-react";

const storageKey = "litegate-theme";

export type Theme = "light" | "dark";

export function applyStoredTheme() {
  const stored = localStorage.getItem(storageKey);
  const theme: Theme = stored === "dark" ? "dark" : "light";
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );

  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    localStorage.setItem(storageKey, next);
    document.documentElement.classList.toggle("dark", next === "dark");
    document.documentElement.style.colorScheme = next;
    setTheme(next);
  }

  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? "Use light theme" : "Use dark theme"}
      title={dark ? "Use light theme" : "Use dark theme"}
      className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
