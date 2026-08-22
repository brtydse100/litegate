import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

interface AuthConfig { sso_enabled: boolean; local_enabled: boolean; }

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
    <div className="flex h-screen items-center justify-center bg-[#0F1117]">
      <div className="w-full max-w-sm rounded-2xl border border-[#2A2E42] bg-[#1A1D27] p-10 flex flex-col items-center gap-6">
        {/* Logo */}
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600 shadow-lg shadow-indigo-600/30">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
        </div>

        <div className="text-center">
          <h1 className="text-2xl font-bold tracking-tight text-white">LiteGate</h1>
          <p className="mt-1.5 text-sm text-gray-400">Your LiteLLM key portal</p>
        </div>

        {isLoading && (
          <div className="h-10 w-full rounded-lg bg-[#22263A] animate-pulse" />
        )}

        {/* SSO button */}
        {showSso && (
          <a href="/api/auth/login"
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-indigo-500 transition-colors shadow-md shadow-indigo-600/20">
            Sign in with SSO
          </a>
        )}

        {showDivider && (
          <div className="flex w-full items-center gap-3">
            <div className="flex-1 h-px bg-[#2A2E42]" />
            <span className="text-xs text-gray-600">or</span>
            <div className="flex-1 h-px bg-[#2A2E42]" />
          </div>
        )}

        {/* Local login — always visible when enabled, no toggle */}
        {showLocal && (
          <form onSubmit={handleLocal} className="w-full space-y-3">
            <label className="block space-y-1 text-xs text-gray-400"><span>Username</span><input
              type="text" placeholder="Username" value={username}
              onChange={e => setUsername(e.target.value)} required autoFocus={!showSso} autoComplete="username"
              className="w-full rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none"
            /></label>
            <label className="block space-y-1 text-xs text-gray-400"><span>Password</span><input
              type="password" placeholder="Password" value={password}
              onChange={e => setPassword(e.target.value)} required autoComplete="current-password"
              className="w-full rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none"
            /></label>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button type="submit" disabled={submitting}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors">
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        <p className="text-xs text-gray-600">Access is granted after your organisation login</p>
      </div>
    </div>
  );
}
