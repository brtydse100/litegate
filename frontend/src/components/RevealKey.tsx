import { useState } from "react";
import { Check, Copy, Eye } from "lucide-react";
import { api } from "../api/client";

export default function RevealKey({
  identifier,
  buttonClassName,
}: {
  identifier: string;
  buttonClassName?: string;
}) {
  const [secret, setSecret] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function reveal() {
    setPending(true);
    setError("");
    setCopied(false);
    try {
      const result = await api.revealKey(identifier);
      setSecret(result.key);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setPending(false);
    }
  }

  async function copy() {
    if (!secret) return;
    await navigator.clipboard.writeText(secret);
    setCopied(true);
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => void reveal()}
        disabled={pending}
        className={
          buttonClassName ??
          "inline-flex items-center gap-2 rounded-md border border-indigo-200 px-3 py-2 text-xs font-medium text-indigo-600 hover:bg-indigo-50 disabled:opacity-50"
        }
      >
        <Eye size={18} /> {pending ? "Loading..." : "Show API key"}
      </button>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {secret && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-sm font-medium text-emerald-900">API key</p>
          <div className="mt-3 flex gap-2">
            <code className="min-w-0 flex-1 break-all text-sm text-emerald-800">
              {secret}
            </code>
            <button
              type="button"
              onClick={() => void copy()}
              aria-label="Copy API key"
              className="text-emerald-700"
            >
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </button>
          </div>
          <button
            type="button"
            onClick={() => setSecret(null)}
            className="mt-3 text-xs font-medium text-emerald-700"
          >
            Hide API key
          </button>
        </div>
      )}
    </div>
  );
}
