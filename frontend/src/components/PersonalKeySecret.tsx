import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { api } from "../api/client";

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
      className="min-w-0 sm:max-w-md"
      role="group"
      aria-label="API key secret"
    >
      <div className="flex min-w-0 items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
        {secret ? (
          <>
            <code className="min-w-0 flex-1 break-all font-mono text-xs text-slate-700">
              {secret}
            </code>
            <button
              type="button"
              onClick={() => void copy()}
              aria-label="Copy API key"
              className="shrink-0 text-slate-500 hover:text-slate-900"
            >
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </button>
            <button
              type="button"
              onClick={hide}
              aria-label="Hide API key"
              className="shrink-0 text-slate-500 hover:text-slate-900"
            >
              <EyeOff size={15} />
            </button>
          </>
        ) : canReveal ? (
          <button
            type="button"
            onClick={() => void reveal()}
            disabled={pending}
            className="inline-flex items-center gap-2 text-xs text-indigo-600 disabled:opacity-50"
          >
            <Eye size={15} />
            {pending ? "Loading API key..." : "Show API key"}
          </button>
        ) : (
          <span className="text-xs text-slate-500">
            Original key unavailable
          </span>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
