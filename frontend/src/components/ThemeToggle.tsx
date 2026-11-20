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

export default function ThemeToggle({
  className = "flex h-8 w-8 items-center justify-center rounded-md text-ink-4 transition-colors hover:bg-well hover:text-ink",
  showLabel = false,
  role,
}: {
  className?: string;
  showLabel?: boolean;
  /** Set to `menuitem` when the toggle sits inside a menu. */
  role?: "menuitem";
}) {
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
  const label = dark ? "Use light theme" : "Use dark theme";
  return (
    <button
      type="button"
      role={role}
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      className={className}
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
      {showLabel && <span>{dark ? "Light theme" : "Dark theme"}</span>}
    </button>
  );
}
