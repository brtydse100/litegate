import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { LogOut, Zap, type LucideIcon } from "lucide-react";
import ThemeToggle from "./ThemeToggle";

/** Logo tile and product name; a configured logo replaces the default mark. */
export function BrandMark({ logoUrl }: { logoUrl?: string }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2.5 text-[17px] font-bold text-paper">
      {logoUrl ? (
        <img
          src={logoUrl}
          alt=""
          className="h-7 max-w-[120px] object-contain"
        />
      ) : (
        <span
          aria-hidden="true"
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-ice text-navy"
        >
          <Zap size={15} strokeWidth={2.4} />
        </span>
      )}
      LiteGate
    </span>
  );
}

export function initials(email?: string) {
  const name = email?.split("@")[0] ?? "";
  const parts = name.split(/[._-]+/).filter(Boolean);
  const letters =
    parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2);
  return letters.toUpperCase() || "LG";
}

export function Avatar({
  email,
  size = "h-[30px] w-[30px]",
}: {
  email?: string;
  size?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex ${size} shrink-0 items-center justify-center rounded-full bg-[#E5F0F4] text-[11px] font-bold text-[#3F6878]`}
    >
      {initials(email)}
    </span>
  );
}

/** Avatar button that opens a small menu with the theme toggle and sign-out. */
export function UserMenu({
  email,
  role,
  onSignOut,
  compact = false,
  up = false,
}: {
  email?: string;
  role?: string;
  onSignOut: () => void;
  compact?: boolean;
  /** Open above the button, for the sidebar footer. */
  up?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent) {
        if (event.key === "Escape") setOpen(false);
        return;
      }
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const item =
    "flex w-full min-h-11 items-center gap-2.5 rounded-lg px-3 text-left text-sm text-ink-2 hover:bg-canvas";
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-11 items-center gap-2.5 rounded-lg px-1.5 text-sm text-[#E6ECF3] hover:bg-navy-2"
      >
        <Avatar email={email} />
        {!compact && (
          <span className="hidden max-w-[220px] truncate sm:inline">
            {email}
          </span>
        )}
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-30 w-60 rounded-xl ${up ? "bottom-full left-0 mb-2" : "right-0 mt-2"} border border-line bg-card p-1.5 shadow-lg`}
        >
          <div className="border-b border-line-soft px-3 py-2.5 text-sm">
            <p className="truncate font-medium text-ink">{email}</p>
            {role && <p className="capitalize text-ink-4">{role}</p>}
          </div>
          <div className="pt-1.5">
            <ThemeToggle className={item} showLabel />
            <button
              type="button"
              role="menuitem"
              onClick={onSignOut}
              className={item}
            >
              <LogOut size={16} /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function DemoRoleSwitch({
  role,
  pending,
  onSwitch,
}: {
  role?: string;
  pending: boolean;
  onSwitch: (role: "admin" | "user") => void;
}) {
  if (import.meta.env.VITE_DEMO_MODE !== "true") return null;
  return (
    <div
      className="flex items-center rounded-lg bg-navy-2 p-0.5"
      aria-label="Demo role"
    >
      {(["user", "admin"] as const).map((value) => (
        <button
          key={value}
          type="button"
          onClick={() => onSwitch(value)}
          disabled={pending}
          aria-label={`View demo as ${value}`}
          className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize disabled:opacity-50 ${
            role === value
              ? "bg-card text-ink"
              : "text-navy-text hover:text-paper"
          }`}
        >
          {value}
        </button>
      ))}
    </div>
  );
}

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  dot?: "ok" | "bad";
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

const navLink = ({ isActive }: { isActive: boolean }) =>
  `flex shrink-0 items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-sm no-underline ${
    isActive
      ? "bg-navy-2 font-semibold text-paper shadow-[inset_3px_0_0_rgb(var(--ice))]"
      : "text-navy-text hover:bg-navy-2/60 hover:text-paper"
  }`;

/** Navy admin sidebar; becomes a scrolling top row on narrow screens. */
export function AdminSidebar({
  groups,
  logoUrl,
  email,
  role,
  onSignOut,
  extra,
}: {
  extra?: ReactNode;
  groups: NavGroup[];
  logoUrl?: string;
  email?: string;
  role?: string;
  onSignOut: () => void;
}) {
  return (
    <nav
      aria-label="Admin navigation"
      className="flex shrink-0 flex-col gap-0.5 bg-navy px-3.5 py-3 text-sm text-[#E6ECF3] md:h-screen md:w-[236px] md:overflow-y-auto md:py-5"
    >
      <div className="flex items-center justify-between gap-3 px-2 pb-2 md:pb-4">
        <BrandMark logoUrl={logoUrl} />
        <div className="md:hidden">
          <UserMenu email={email} role={role} onSignOut={onSignOut} compact />
        </div>
      </div>
      {extra && <div className="px-2 pb-2">{extra}</div>}
      <div className="flex gap-1 overflow-x-auto pb-1 md:flex-col md:gap-0.5 md:overflow-visible md:pb-0">
        {groups.map((group) => (
          <div key={group.label} className="contents md:block">
            <p className="mx-2.5 mb-1.5 mt-4 hidden text-[11px] font-semibold tracking-[0.06em] text-navy-muted md:block">
              {group.label.toUpperCase()}
            </p>
            {group.items.map((item) => (
              <NavLink key={item.to} to={item.to} className={navLink} end>
                <item.icon size={16} aria-hidden />
                <span className="flex-1">{item.label}</span>
                {item.dot && (
                  <span
                    className={`h-2 w-2 rounded-full ${
                      item.dot === "ok" ? "bg-[#6FD3A8]" : "bg-danger"
                    }`}
                  >
                    <span className="sr-only">
                      {item.dot === "ok" ? "Ready" : "Not ready"}
                    </span>
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-auto hidden items-center gap-1 border-t border-navy-3 pt-3.5 md:flex">
        <UserMenu email={email} role={role} onSignOut={onSignOut} compact up />
        <span className="min-w-0 text-[13px] leading-tight">
          <span className="block truncate">{email}</span>
          <span className="capitalize text-navy-muted">{role}</span>
        </span>
      </div>
    </nav>
  );
}
