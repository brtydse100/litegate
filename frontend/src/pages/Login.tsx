import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../hooks/useAuth";
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
    <div className="flex min-h-screen flex-col bg-canvas lg:flex-row">
      <section
        aria-label="LiteGate"
        className="flex flex-col justify-between gap-6 bg-navy px-6 py-8 text-paper sm:px-10 lg:w-[44%] lg:max-w-[560px] lg:px-14 lg:py-14"
      >
        <div className="flex flex-col gap-6 lg:gap-10">
          {cfg?.logo_url ? (
            <img
              src={cfg.logo_url}
              alt="Organization logo"
              className="h-11 max-w-[220px] self-start object-contain"
            />
          ) : (
            <span
              aria-hidden="true"
              className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-ice text-navy"
            >
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
            </span>
          )}
          <div>
            <h1 className="text-[28px] font-bold tracking-[-0.01em] lg:text-4xl">
              LiteGate
            </h1>
            <p className="mt-2 max-w-md whitespace-pre-line break-words text-[15px] leading-relaxed text-navy-text">
              {cfg?.login_text?.trim()
                ? cfg.login_text
                : "Sign in to your LiteLLM access portal"}
            </p>
          </div>
        </div>
        <p className="hidden text-[13px] text-navy-muted lg:block">
          Access is granted through your organization
        </p>
      </section>

      <main className="relative flex flex-1 items-center justify-center px-4 py-10 sm:px-8">
        <div className="absolute right-4 top-4 rounded-lg border border-line bg-card">
          <ThemeToggle />
        </div>
        <div className="flex w-full max-w-[380px] flex-col gap-5 rounded-2xl border border-line bg-card p-7 sm:p-9">
          <h2 className="text-xl font-bold text-ink">Sign in</h2>

          {isLoading && (
            <div className="h-11 w-full animate-pulse rounded-lg bg-well" />
          )}

          {isError && (
            <div className="rounded-lg border border-danger-line bg-danger-tint p-3 text-sm text-danger">
              <p>Sign-in configuration is temporarily unavailable.</p>
              <button
                type="button"
                onClick={() => void refetch()}
                className="mt-2 font-semibold underline underline-offset-2"
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
              <div className="h-px flex-1 bg-line" />
              <span className="text-xs text-ink-4">or</span>
              <div className="h-px flex-1 bg-line" />
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

          <p className="text-center text-xs text-ink-4 lg:hidden">
            Access is granted through your organization
          </p>
        </div>
      </main>
    </div>
  );
}
