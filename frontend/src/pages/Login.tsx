import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

interface AuthConfig {
  sso_enabled: boolean;
  local_enabled: boolean;
}

async function fetchAuthConfig(): Promise<AuthConfig> {
  const r = await fetch("/api/auth/config");
  if (!r.ok) return { sso_enabled: false, local_enabled: false };
  return r.json();
}

async function localLogin(username: string, password: string): Promise<void> {
  const body = new FormData();
  body.append("username", username);
  body.append("password", password);
  const r = await fetch("/api/auth/local", { method: "POST", body });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(err.detail ?? "Login failed");
  }
  await r.json();
}

export default function Login() {
  const navigate = useNavigate();
  const { login, user } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { data: cfg, isLoading } = useQuery<AuthConfig>({
    queryKey: ["auth-config"],
    queryFn: fetchAuthConfig,
    staleTime: Infinity,
  });

  const showSso = !isLoading && cfg?.sso_enabled;
  const showLocal = !isLoading && cfg?.local_enabled;
  const showDivider = showSso && showLocal;

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [navigate, user]);

  async function handleLocal(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await localLogin(username, password);
      await login();
      navigate("/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-50 px-4 py-10">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-indigo-50 to-transparent" />
      <div className="relative flex w-full max-w-sm flex-col items-center gap-6 rounded-xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/60 sm:p-10">
        {/* Logo */}
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-lg shadow-indigo-200">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
        </div>

        <div className="text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950">
            LiteGate
          </h1>
          <p className="mt-1.5 text-sm text-slate-500">
            Sign in to your LiteLLM access portal
          </p>
        </div>

        {isLoading && (
          <div className="h-10 w-full animate-pulse rounded-md bg-slate-100" />
        )}

        {/* SSO button */}
        {showSso && (
          <a
            href="/api/auth/login"
            className="w-full rounded-md bg-indigo-600 px-4 py-2.5 text-center text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700"
          >
            Sign in with SSO
          </a>
        )}

        {showDivider && (
          <div className="flex w-full items-center gap-3">
            <div className="h-px flex-1 bg-slate-200" />
            <span className="text-xs text-slate-400">or</span>
            <div className="h-px flex-1 bg-slate-200" />
          </div>
        )}

        {/* Local login — always visible when enabled, no toggle */}
        {showLocal && (
          <form onSubmit={handleLocal} className="w-full space-y-3">
            <label className="block space-y-1.5 text-xs font-medium text-slate-700">
              <span>Username</span>
              <input
                type="text"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus={!showSso}
                autoComplete="username"
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
            </label>
            <label className="block space-y-1.5 text-xs font-medium text-slate-700">
              <span>Password</span>
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
            </label>
            {error && <p className="text-xs text-red-700">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:opacity-50"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        <p className="text-center text-xs leading-5 text-slate-400">
          Access is granted through your organization
        </p>
      </div>
    </div>
  );
}
