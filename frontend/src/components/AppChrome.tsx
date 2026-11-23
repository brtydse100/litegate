import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type React from "react";
import { Link, useLocation } from "react-router-dom";
import { BookOpen, LogOut, type LucideIcon } from "lucide-react";
import EmailAddress from "./EmailAddress";
import LogoMark from "./LogoMark";
import ThemeToggle from "./ThemeToggle";

/** Logo tile and product name; a configured logo replaces the default mark. */
export function BrandMark({ logoUrl }: { logoUrl?: string }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2.5 text-[17px] font-semibold tracking-[-0.01em] text-ink">
      {logoUrl ? (
        <span className="inline-flex h-8 shrink-0 items-center rounded-lg bg-paper px-1.5 ring-1 ring-line-soft">
          <img
            src={logoUrl}
            alt=""
            className="h-6 max-w-[120px] object-contain"
          />
        </span>
      ) : (
        <LogoMark size={28} />
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
      className={`inline-flex ${size} shrink-0 items-center justify-center rounded-full bg-ink-5 text-xs font-semibold text-paper`}
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
  apiDocsUrl,
}: {
  email?: string;
  role?: string;
  onSignOut: () => void;
  /** Administrators get the built-in API reference here. */
  apiDocsUrl?: string;
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
    "flex w-full min-h-9 items-center gap-2.5 rounded-md px-2.5 text-left text-sm text-ink hover:bg-blue-solid hover:text-paper focus:bg-blue-solid focus:text-paper focus:outline-none";
  return (
    <div ref={root} className="relative flex items-center gap-1">
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
        className="inline-flex min-h-11 items-center gap-2.5 rounded-lg px-1.5 text-sm text-ink transition-colors duration-150 hover:bg-ink/[0.06]"
      >
        <Avatar email={email} />
      </button>
      {/* Beside the button, not inside it: the address has its own copy
          button, as it did before the redesign. */}
      {!compact && email && (
        <span className="hidden max-w-[240px] text-sm text-ink-2 sm:inline">
          <EmailAddress email={email} />
        </span>
      )}
      {open && (
        <div
          ref={menu}
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKey}
          className={`absolute z-30 rounded-xl ${up ? "bottom-full left-0 mb-2 w-52" : "right-0 mt-2 w-60 max-w-[calc(100vw-2rem)]"} border border-line-soft bg-card/95 p-1.5 shadow-[0_10px_30px_rgb(0_0_0/0.16),0_1px_3px_rgb(0_0_0/0.08)] backdrop-blur-xl`}
        >
          <div className="border-b border-line-soft px-2.5 pb-2 pt-1.5 text-sm">
            {email && (
              <EmailAddress email={email} className="font-medium text-ink" />
            )}
            {role && (
              <p className="text-[13px] capitalize text-ink-4">{role}</p>
            )}
          </div>
          <div className="pt-1">
            <ThemeToggle className={item} showLabel role="menuitem" />
            {apiDocsUrl && (
              <a
                role="menuitem"
                href={apiDocsUrl}
                target="_blank"
                rel="noreferrer"
                className={`${item} no-underline`}
              >
                <BookOpen size={16} aria-hidden="true" /> API reference
              </a>
            )}
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

/** Demo-only roles; team owners see just their part of the organization. */
export type DemoRole =
  "user" | "admin" | "platform-owner" | "infrastructure-owner";

const ownerTeams: Array<{ role: DemoRole; label: string; name: string }> = [
  {
    role: "platform-owner",
    label: "People",
    name: "Own Platform, a team of people",
  },
  {
    role: "infrastructure-owner",
    label: "Teams",
    name: "Own Infrastructure, a team of teams",
  },
];

export function DemoRoleSwitch({
  role,
  pending,
  onSwitch,
}: {
  role?: DemoRole;
  pending: boolean;
  onSwitch: (role: DemoRole) => void;
}) {
  if (import.meta.env.VITE_DEMO_MODE !== "true") return null;
  const owner = role === "platform-owner" || role === "infrastructure-owner";
  const segment = (active: boolean) =>
    `flex-1 whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium transition-colors duration-150 disabled:opacity-50 ${
      active
        ? "bg-segment text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12),0_0_0_0.5px_rgb(0_0_0/0.04)]"
        : "text-ink-3 hover:text-ink"
    }`;
  return (
    <div className="flex flex-col gap-1" aria-label="Demo role">
      <div className="flex items-center rounded-lg bg-ink/[0.06] p-0.5">
        {[
          { value: "user" as const, label: "User", active: role === "user" },
          {
            value: "platform-owner" as const,
            label: "Owner",
            active: owner,
          },
          { value: "admin" as const, label: "Admin", active: role === "admin" },
        ].map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => !item.active && onSwitch(item.value)}
            disabled={pending}
            aria-pressed={item.active}
            aria-label={`View demo as ${item.value === "platform-owner" ? "team owner" : item.label.toLowerCase()}`}
            className={segment(item.active)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {owner && (
        <div className="flex items-center rounded-lg bg-ink/[0.06] p-0.5">
          {ownerTeams.map((item) => (
            <button
              key={item.role}
              type="button"
              onClick={() => role !== item.role && onSwitch(item.role)}
              disabled={pending}
              aria-pressed={role === item.role}
              aria-label={item.name}
              className={segment(role === item.role)}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
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
  `flex shrink-0 items-center gap-2.5 rounded-md px-2.5 py-2 text-sm no-underline transition-colors duration-150 ${
    isActive
      ? "bg-ink/[0.09] font-medium text-ink [&>svg]:text-blue"
      : "text-ink hover:bg-ink/[0.05] [&>svg]:text-blue"
  }`;

const sidebarThemeButton =
  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-4 transition-colors duration-150 hover:bg-ink/[0.06] hover:text-ink";

/** Light sidebar, as in macOS; becomes a scrolling top row on narrow screens. */
export function AdminSidebar({
  groups,
  logoUrl,
  email,
  role,
  onSignOut,
  apiDocsUrl,
  extra,
}: {
  extra?: ReactNode;
  apiDocsUrl?: string;
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
      className="flex shrink-0 flex-col gap-0.5 border-b border-line-soft bg-sidebar px-3 py-3 text-sm text-ink md:h-screen md:w-[236px] md:overflow-y-auto md:border-b-0 md:border-r md:py-5"
    >
      <div className="flex items-center justify-between gap-3 px-2 pb-2 md:pb-4">
        <BrandMark logoUrl={logoUrl} />
        <div className="flex items-center gap-1 md:hidden">
          <ThemeToggle className={sidebarThemeButton} />
          <UserMenu
            email={email}
            role={role}
            onSignOut={onSignOut}
            apiDocsUrl={apiDocsUrl}
            compact
          />
        </div>
      </div>
      {extra && <div className="px-2 pb-2">{extra}</div>}
      <div
        ref={row}
        className="flex gap-1 overflow-x-auto pb-1 [scrollbar-width:none] md:flex-col md:gap-0.5 md:overflow-visible md:pb-0 [&::-webkit-scrollbar]:hidden"
      >
        {groups.map((group) => (
          <div key={group.label} className="contents md:block">
            <p className="mx-2.5 mb-1 mt-4 hidden text-xs font-semibold text-ink-4 md:block">
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
                      item.dot === "ok" ? "bg-green" : "bg-danger"
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
      {/* Its own row, so long email addresses keep their full width. */}
      <ThemeToggle
        showLabel
        className={`${navLink(false)} mt-auto hidden w-full md:flex`}
      />
      <div className="mt-2 hidden items-center gap-1 border-t border-line pt-3 md:flex">
        <UserMenu
          email={email}
          role={role}
          onSignOut={onSignOut}
          apiDocsUrl={apiDocsUrl}
          compact
          up
        />
        <span className="min-w-0 flex-1 text-[13px] leading-tight">
          {email && <EmailAddress email={email} className="block" />}
          <span className="block capitalize text-ink-4">{role}</span>
        </span>
      </div>
    </nav>
  );
}
