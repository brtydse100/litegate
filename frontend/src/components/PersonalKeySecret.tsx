import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { api } from "../api/client";
import { primaryKeyActionClassName } from "./keyActionStyles";

interface Props {
  identifier: string;
  canReveal: boolean;
  initialSecret?: string | null;
  onHide?: () => void;
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

  return (
    <div
      className="w-full min-w-0 space-y-3"
      role="group"
      aria-label="API key secret"
    >
      {secret ? (
        <div className="flex min-w-0 flex-wrap items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-4 shadow-sm">
          <code className="min-w-0 basis-full break-all font-mono text-base font-medium leading-relaxed text-slate-900 sm:flex-1 sm:basis-auto md:text-lg">
            {secret}
          </code>
          <button
            type="button"
            onClick={() => void copy()}
            aria-label="Copy API key"
            className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-xs font-semibold text-indigo-50 hover:bg-indigo-700"
          >
            {copied ? <Check size={17} /> : <Copy size={17} />}
            {copied ? "Copied" : "Copy API key"}
          </button>
        </div>
      ) : !canReveal ? (
        <span className="text-xs text-slate-500">Original key unavailable</span>
      ) : null}
      {(secret || canReveal) && (
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
      )}
      {error && (
        <p role="alert" className="mt-1 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
