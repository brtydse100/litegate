import { useState, type ReactNode } from "react";
import { X } from "lucide-react";

/**
 * A message box the reader can close. It keeps the caller's styling and
 * reappears when `messageKey` changes, so a new message is never hidden.
 */
export default function DismissibleMessage({
  messageKey,
  className,
  role = "status",
  children,
}: {
  messageKey: string;
  className: string;
  role?: "status" | "alert";
  children: ReactNode;
}) {
  const [dismissed, setDismissed] = useState<string | null>(null);
  if (dismissed === messageKey) return null;
  return (
    <div role={role} className={`flex items-start gap-3 ${className}`}>
      <div className="min-w-0 flex-1">{children}</div>
      <button
        type="button"
        aria-label="Dismiss message"
        onClick={() => setDismissed(messageKey)}
        className="-mr-1 shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
      >
        <X size={14} />
      </button>
    </div>
  );
}
