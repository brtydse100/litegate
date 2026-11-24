import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import LogoMark from "../components/LogoMark";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../hooks/useAuth";
import { useFavicon } from "../hooks/useFavicon";
import { buttonPrimary, fieldInput, fieldLabel } from "../components/ui";

interface AuthConfig {
  sso_enabled: boolean;
  local_enabled: boolean;
  login_text: string;
  logo_url: string;
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const r = await fetch("/api/auth/config");
  if (!r.ok)
    throw new Error("Sign-in configuration is temporarily unavailable");
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

  const {
    data: cfg,
    isLoading,
    isError,
    refetch,
  } = useQuery<AuthConfig>({
    queryKey: ["auth-config"],
    queryFn: fetchAuthConfig,
    staleTime: Infinity,
  });
  useFavicon(cfg?.logo_url);

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
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-canvas px-4 py-12">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <main className="flex w-full max-w-[360px] flex-col items-center gap-7">
        <section
          aria-label="LiteGate"
          className="flex flex-col items-center gap-4 text-center"
        >
          <LogoMark
            size={64}
            src={cfg?.logo_url || undefined}
            alt="Organization logo"
            className="rounded-[15px] shadow-[0_4px_12px_rgb(0_0_0/0.12),0_1px_2px_rgb(0_0_0/0.08)]"
          />
          <div>
            <h1 className="text-[28px] font-bold tracking-[-0.02em] text-ink">
              LiteGate
            </h1>
            <p className="mt-1 max-w-sm whitespace-pre-line break-words text-[15px] leading-snug text-ink-4">
              {cfg?.login_text?.trim()
                ? cfg.login_text
                : "Sign in to your LiteLLM access portal"}
            </p>
          </div>
        </section>
        <div className="flex w-full flex-col gap-4 rounded-2xl border border-line-soft bg-card p-6 shadow-[0_1px_3px_rgb(0_0_0/0.04)]">
          <h2 className="text-[17px] font-semibold text-ink">Sign in</h2>

          {isLoading && (
            <div className="h-11 w-full animate-pulse rounded-lg bg-well" />
          )}

          {isError && (
            <div className="rounded-xl bg-danger-tint px-3.5 py-3 text-sm text-danger">
              <p>Sign-in configuration is temporarily unavailable.</p>
              <button
                type="button"
                onClick={() => void refetch()}
                className="mt-1.5 font-medium underline underline-offset-2"
              >
                Try again
              </button>
            </div>
          )}

          {showSso && (
            <a
              href="/api/auth/login"
              className={`${buttonPrimary} w-full no-underline`}
            >
              Sign in with SSO
            </a>
          )}

          {showDivider && (
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-line-soft" />
              <span className="text-[13px] text-ink-4">or</span>
              <div className="h-px flex-1 bg-line-soft" />
            </div>
          )}

          {showLocal && (
            <form onSubmit={handleLocal} className="flex flex-col gap-3.5">
              <label className={fieldLabel}>
                <span>Username</span>
                <input
                  type="text"
                  placeholder="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus={!showSso}
                  autoComplete="username"
                  className={fieldInput}
                />
              </label>
              <label className={fieldLabel}>
                <span>Password</span>
                <input
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  className={fieldInput}
                />
              </label>
              {error && (
                <p role="alert" className="text-sm text-danger">
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={submitting}
                className={`${buttonPrimary} mt-1 w-full`}
              >
                {submitting ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}
        </div>
        <p className="text-center text-[13px] text-ink-4">
          Access is granted through your organization
        </p>
      </main>
    </div>
  );
}
