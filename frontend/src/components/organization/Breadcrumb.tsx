import { Fragment } from "react";
import { ChevronRight } from "lucide-react";

interface Crumb {
  id: string;
  name: string;
}

/**
 * Path to the selected group. Each step opens that group; "Organization"
 * closes the selection. Ancestors not loaded yet are left out.
 */
export default function Breadcrumb({
  trail,
  onOpen,
  onClose,
}: {
  /** From the top-level group down to the selected one. */
  trail: Crumb[];
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  if (!trail.length) return null;
  const link =
    "rounded-md px-1.5 py-0.5 text-ink-4 transition-colors duration-150 hover:bg-ink/[0.06] hover:text-ink";
  const separator = (
    <ChevronRight
      size={13}
      aria-hidden="true"
      className="shrink-0 text-ink-5"
    />
  );
  return (
    <nav aria-label="Breadcrumb" className="-mx-1.5 -mb-3">
      <ol className="flex flex-wrap items-center gap-0.5 text-[13px]">
        <li>
          <button type="button" onClick={onClose} className={link}>
            Organization
          </button>
        </li>
        {trail.map((crumb, index) => (
          <Fragment key={crumb.id}>
            <li aria-hidden="true">{separator}</li>
            <li>
              {index === trail.length - 1 ? (
                <span
                  aria-current="page"
                  className="px-1.5 font-medium text-ink"
                >
                  {crumb.name}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => onOpen(crumb.id)}
                  className={link}
                >
                  {crumb.name}
                </button>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
