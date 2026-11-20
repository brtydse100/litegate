import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { api } from "../api/client";
import DismissibleMessage from "./DismissibleMessage";

interface Props {
  identifier: string;
  canReveal: boolean;
  initialSecret?: string | null;
  onHide?: () => void;
  /** Masked preview shown while the secret is hidden. */
  preview?: string;
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
  preview = "sk-••••••••••••••••",
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
      className="flex w-full min-w-0 flex-col gap-2"
      role="group"
      aria-label="API key secret"
    >
      <div
        className={`flex flex-wrap items-center gap-2 rounded-[10px] py-1.5 pl-4 pr-1.5 ${
          secret ? "bg-mint-tint" : "bg-canvas"
        }`}
      >
        <code
          className={`min-w-0 flex-[1_1_240px] break-all py-2 font-mono text-[15px] ${
            secret ? "text-mint-ink" : "text-ink"
          }`}
        >
          {secret ?? preview}
        </code>
        {(secret || canReveal) && (
          <button
            type="button"
            onClick={() => (secret ? hide() : void reveal())}
            disabled={pending}
            aria-expanded={!!secret}
            aria-label={
              pending
                ? "Loading API key"
                : secret
                  ? "Hide API key"
                  : "Show API key"
            }
            className="min-h-11 rounded-lg px-3.5 py-2 text-sm text-ink-2 hover:bg-well disabled:opacity-50"
          >
            {pending ? "Loading…" : secret ? "Hide" : "Show"}
          </button>
        )}
        {secret && (
          <button
            type="button"
            onClick={() => void copy()}
            aria-label="Copy API key"
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-line-input bg-card px-4 py-2 text-sm font-semibold text-ink hover:bg-canvas"
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}
            {copied ? "Copied" : "Copy"}
            <span className="sr-only" role="status">
              {copied ? "Copied" : ""}
            </span>
          </button>
        )}
      </div>
      {!secret && !canReveal && (
        <p className="text-xs text-ink-4">
          LiteGate has no saved copy of this key to show. The key itself still
          works.
        </p>
      )}
      {error && (
        <DismissibleMessage
          role="alert"
          messageKey={error}
          className="text-xs text-danger"
        >
          {error}
        </DismissibleMessage>
      )}
    </div>
  );
}
