import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type React from "react";
import { Link, useLocation } from "react-router-dom";
import { LogOut, Zap, type LucideIcon } from "lucide-react";
import ThemeToggle from "./ThemeToggle";

/** Logo tile and product name; a configured logo replaces the default mark. */
export function BrandMark({ logoUrl }: { logoUrl?: string }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2.5 text-[17px] font-bold text-paper">
      {logoUrl ? (
        <span className="inline-flex h-8 shrink-0 items-center rounded-lg bg-paper px-1.5">
          <img
            src={logoUrl}
            alt=""
            className="h-6 max-w-[120px] object-contain"
          />
        </span>
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
      className={`inline-flex ${size} shrink-0 items-center justify-center rounded-full bg-cyan-tint text-[11px] font-bold text-cyan-ink`}
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
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const items = () =>
    Array.from(
      menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
    );
  useEffect(() => {
    if (!open) return;
    items()[0]?.focus();
    function close(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  // Menu keyboard pattern: arrows move, Home/End jump, Escape returns focus.
  function onMenuKey(event: React.KeyboardEvent) {
    const list = items();
    const index = list.indexOf(document.activeElement as HTMLElement);
    const move = (next: number) => {
      event.preventDefault();
      list[(next + list.length) % list.length]?.focus();
    };
    if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(list.length - 1);
    else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    } else if (event.key === "Tab") setOpen(false);
  }
  const item =
    "flex w-full min-h-11 items-center gap-2.5 rounded-lg px-3 text-left text-sm text-ink-2 hover:bg-canvas";
  return (
    <div ref={root} className="relative">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
        className="inline-flex min-h-11 items-center gap-2.5 rounded-lg px-1.5 text-sm text-navy-ink hover:bg-navy-2"
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
          ref={menu}
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKey}
          className={`absolute z-30 rounded-xl ${up ? "bottom-full left-0 mb-2 w-52" : "right-0 mt-2 w-60 max-w-[calc(100vw-2rem)]"} border border-line bg-card p-1.5 shadow-lg`}
        >
          <div className="border-b border-line-soft px-3 py-2.5 text-sm">
            <p className="truncate font-medium text-ink">{email}</p>
            {role && <p className="capitalize text-ink-4">{role}</p>}
          </div>
          <div className="pt-1.5">
            <ThemeToggle className={item} showLabel role="menuitem" />
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

const navLink = (isActive: boolean) =>
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
  const location = useLocation();
  const row = useRef<HTMLDivElement>(null);
  const items = groups.flatMap((group) => group.items);
  const links = items.map((item) => `${item.to}:${item.dot ?? ""}`).join("|");
  // On phones the links form a scrolling row; keep the current one visible,
  // including after late links or status dots shift the row.
  useLayoutEffect(() => {
    const box = row.current;
    const current = box?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!box || !current || box.scrollWidth <= box.clientWidth) return;
    const link = current.getBoundingClientRect();
    const edges = box.getBoundingClientRect();
    if (link.left < edges.left) box.scrollLeft -= edges.left - link.left + 8;
    else if (link.right > edges.right)
      box.scrollLeft += link.right - edges.right + 8;
  }, [location.pathname, location.hash, links]);
  // A link with a #section is active only on that section, and the plain
  // link to the same page steps aside while the section is shown.
  const pathname = location.pathname.replace(/(.)\/+$/, "$1");
  const isActive = (to: string) => {
    const [path, hash = ""] = to.split("#");
    if (pathname !== path) return false;
    if (hash) return location.hash === `#${hash}`;
    return !items.some(
      (item) => item.to === `${path}${location.hash}` && location.hash,
    );
  };
  return (
    <nav
      aria-label="Admin navigation"
      className="flex shrink-0 flex-col gap-0.5 bg-navy px-3.5 py-3 text-sm text-navy-ink md:h-screen md:w-[236px] md:overflow-y-auto md:py-5"
    >
      <div className="flex items-center justify-between gap-3 px-2 pb-2 md:pb-4">
        <BrandMark logoUrl={logoUrl} />
        <div className="md:hidden">
          <UserMenu email={email} role={role} onSignOut={onSignOut} compact />
        </div>
      </div>
      {extra && <div className="px-2 pb-2">{extra}</div>}
      <div
        ref={row}
        className="flex gap-1 overflow-x-auto pb-1 md:flex-col md:gap-0.5 md:overflow-visible md:pb-0"
      >
        {groups.map((group) => (
          <div key={group.label} className="contents md:block">
            <p className="mx-2.5 mb-1.5 mt-4 hidden text-[11px] font-semibold uppercase tracking-[0.06em] text-navy-muted md:block">
              {group.label}
            </p>
            {group.items.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                aria-current={isActive(item.to) ? "page" : undefined}
                className={navLink(isActive(item.to))}
              >
                <item.icon size={16} aria-hidden />
                <span className="flex-1">{item.label}</span>
                {item.dot && (
                  <span
                    className={`relative h-2 w-2 rounded-full ${
                      item.dot === "ok" ? "bg-ready" : "bg-alert"
                    }`}
                  >
                    <span className="sr-only">
                      {item.dot === "ok" ? "Ready" : "Not ready"}
                    </span>
                  </span>
                )}
              </Link>
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
