import { useState } from "react";
import { Copy } from "lucide-react";

export default function EmailAddress({
  email,
  className = "",
}: {
  email: string;
  className?: string;
}) {
  const [status, setStatus] = useState("");
  async function copy(event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(email);
      setStatus("Email copied");
    } catch {
      setStatus("Could not copy email. Select and copy the address.");
    }
  }
  return (
    <span
      className={`inline-flex min-w-0 max-w-full items-start gap-1 ${className}`}
    >
      <span className="min-w-0 break-all whitespace-normal select-text">
        {email}
      </span>
      <button
        type="button"
        aria-label={`Copy email ${email}`}
        title="Copy email"
        onClick={(event) => void copy(event)}
        className="shrink-0 rounded p-1 hover:bg-canvas focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue"
      >
        <Copy size={12} aria-hidden="true" />
      </button>
      {status && (
        <span role="status" className="sr-only">
          {status}
        </span>
      )}
    </span>
  );
}
