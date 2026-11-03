import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { api } from "../api/client";
import { primaryKeyActionClassName } from "./keyActionStyles";

interface Props {
  identifier: string;
  canReveal: boolean;
  initialSecret?: string | null;
  onHide?: () => void;
  children?: (action: ReactNode) => ReactNode;
}

export default function PersonalKeySecret(props: Props) {
  return (
    <SecretContent key={`${props.identifier}:${props.canReveal}`} {...props} />
  );
}

function SecretContent({
  identifier,
  canReveal,
  initialSecret,
  onHide,
  children,
}: Props) {
  const [secret, setSecret] = useState<string | null>(initialSecret ?? null);
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const reveal = useCallback(async () => {
    const request = ++requestId.current;
    setPending(true);
    setError("");
    setCopied(false);
    try {
      const result = await api.revealKey(identifier);
      if (request === requestId.current) setSecret(result.key);
    } catch (cause) {
      if (request === requestId.current) setError((cause as Error).message);
    } finally {
      if (request === requestId.current) setPending(false);
    }
  }, [identifier]);

  useEffect(() => {
    if (canReveal && identifier) void reveal();
    return () => {
      requestId.current += 1;
    };
  }, [canReveal, identifier, reveal]);

  useEffect(() => {
    if (initialSecret) {
      requestId.current += 1;
      setSecret(initialSecret);
      setPending(false);
      setCopied(false);
      setError("");
    }
  }, [initialSecret]);

  async function copy() {
    if (!secret) return;
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setError("Could not copy the API key. Select it and copy manually.");
    }
  }

  function hide() {
    requestId.current += 1;
    setSecret(null);
    setPending(false);
    setCopied(false);
    setError("");
    onHide?.();
  }

  const action =
    secret || canReveal ? (
      <button
        type="button"
        onClick={() => (secret ? hide() : void reveal())}
        disabled={pending}
        aria-expanded={!!secret}
        className={primaryKeyActionClassName}
      >
        {secret ? <EyeOff size={21} /> : <Eye size={21} />}
        {pending
          ? "Loading API key..."
          : secret
            ? "Hide API key"
            : "Show API key"}
      </button>
    ) : null;

  return (
    <div
      className="w-full min-w-0 space-y-6"
      role="group"
      aria-label="API key secret"
    >
      {secret ? (
        <div className="flex min-w-0 items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
          <code className="min-w-0 flex-1 break-all font-mono text-sm leading-relaxed text-emerald-900">
            {secret}
          </code>
          <button
            type="button"
            onClick={() => void copy()}
            aria-label="Copy API key"
            title={copied ? "Copied" : "Copy API key"}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-emerald-900 hover:bg-emerald-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 [html.dark_&]:hover:bg-emerald-900"
          >
            {copied ? <Check size={17} /> : <Copy size={17} />}
            <span className="sr-only" role="status">
              {copied ? "Copied" : ""}
            </span>
          </button>
        </div>
      ) : !canReveal ? (
        <span className="text-xs text-slate-500">Original key unavailable</span>
      ) : null}
      {children ? children(action) : action}
      {error && (
        <p role="alert" className="mt-1 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
