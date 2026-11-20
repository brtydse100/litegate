import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Info, Shield, UserPlus } from "lucide-react";
import { api } from "../api/client";
import { useOperationLimit } from "../hooks/useOperationLimit";
import { useDialogDismiss } from "../hooks/useDialogDismiss";
import EmailAddress from "./EmailAddress";
import PeopleDirectory from "./PeopleDirectory";
import DismissibleMessage from "./DismissibleMessage";
import { Avatar } from "./AppChrome";
import { PageHeader, Pill } from "./Page";
import {
  buttonPrimary,
  buttonSecondary,
  buttonSmall,
  card,
  cardHeader,
  cardTitle,
  fieldInput,
  fieldLabel,
  tableHead,
} from "./ui";

export default function AdminUsers({
  localUsersEnabled = true,
}: {
  localUsersEnabled?: boolean;
}) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [resetUsername, setResetUsername] = useState<string | null>(null);
  const [replacementPassword, setReplacementPassword] = useState("");
  const { operationsBlocked, retryAfter, refreshOperationLimit } =
    useOperationLimit();

  const users = useQuery({
    queryKey: ["local-users"],
    queryFn: api.listUsers,
    enabled: localUsersEnabled,
  });
  const create = useMutation({
    mutationFn: api.createUser,
    onSuccess: () => {
      setUsername("");
      setEmail("");
      setPassword("");
      setRole("user");
      void queryClient.invalidateQueries({ queryKey: ["local-users"] });
    },
    onSettled: refreshOperationLimit,
  });
  const update = useMutation({
    mutationFn: ({
      name,
      payload,
    }: {
      name: string;
      payload: { active?: boolean; role?: "user" | "admin"; password?: string };
    }) => api.updateUser(name, payload),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["local-users"] }),
    onSettled: refreshOperationLimit,
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (operationsBlocked || create.isPending || update.isPending) return;
    create.mutate({ username, email, password, role });
  }

  function submitPasswordReset(event: React.FormEvent) {
    event.preventDefault();
    if (
      !resetUsername ||
      replacementPassword.length < 10 ||
      replacementPassword.length > 256 ||
      operationsBlocked ||
      update.isPending
    )
      return;
    update.mutate(
      { name: resetUsername, payload: { password: replacementPassword } },
      {
        onSuccess: () => {
          setResetUsername(null);
          setReplacementPassword("");
        },
      },
    );
  }

  function closeReset() {
    setResetUsername(null);
    setReplacementPassword("");
    update.reset();
  }
  const dialogRef = useDialogDismiss<HTMLFormElement>(
    closeReset,
    update.isPending,
    !!resetUsername,
  );

  const error =
    create.error ?? (resetUsername ? null : update.error) ?? users.error;

  if (!localUsersEnabled)
    return (
      <section className="flex w-full flex-col gap-6">
        <PageHeader
          eyebrow="Manage"
          title="People"
          description="Everyone registered in LiteLLM, including SSO accounts and people without keys."
        />
        <PeopleDirectory />
      </section>
    );

  return (
    <section className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Manage"
        title="People and local access"
        description={
          <>
            Manage password-based accounts for people who cannot sign in with
            your organization&apos;s SSO.
          </>
        }
      />

      <PeopleDirectory />

      <div className="grid gap-3.5 md:grid-cols-3">
        {[
          {
            icon: Info,
            title: "When to use this",
            body: (
              <>
                Create a local account for contractors, emergency access, or
                anyone without SSO. People covered by SSO should keep using SSO.
              </>
            ),
          },
          {
            icon: Shield,
            title: "User or admin?",
            body: (
              <>
                <strong className="text-ink-2">Users</strong> create or
                regenerate their own key.{" "}
                <strong className="text-ink-2">Admins</strong> manage all keys
                and local accounts.
              </>
            ),
          },
          {
            icon: Bot,
            title: "Automation agents",
            body: (
              <>
                Use the management API key for trusted agents that need admin
                automation. Never give an agent a shared human password.
              </>
            ),
          },
        ].map(({ icon: Icon, title, body }) => (
          <div key={title} className={`${card} px-4 py-3.5`}>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Icon size={15} aria-hidden="true" className="text-blue" />
              {title}
            </h2>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-3">
              {body}
            </p>
          </div>
        ))}
      </div>

      {error && (
        <DismissibleMessage
          role="alert"
          messageKey={(error as Error).message}
          className="rounded-xl border border-danger-line bg-danger-tint px-4 py-3 text-sm text-danger"
        >
          {(error as Error).message}
        </DismissibleMessage>
      )}
      {operationsBlocked && (
        <DismissibleMessage
          messageKey="account-actions-paused"
          className="rounded-xl border border-sand/40 bg-sand-tint px-4 py-3 text-sm text-sand-ink"
        >
          Account actions are paused. Try again in {retryAfter || 1} seconds.
        </DismissibleMessage>
      )}

      <section
        aria-label="Local accounts"
        className={`overflow-hidden ${card}`}
      >
        <div className={cardHeader}>
          <div>
            <h2 className={cardTitle}>Local accounts</h2>
            <p className="mt-0.5 text-[13px] text-ink-4">
              <span className="text-ink-2">Reset password</span> replaces the
              current password.{" "}
              <span className="text-ink-2">Make admin/user</span> changes
              management access. <span className="text-ink-2">Disable</span>{" "}
              immediately blocks portal access without deleting the account.
            </p>
          </div>
          {users.data && (
            <span className="text-[13px] text-ink-4">
              {users.data.length}{" "}
              {users.data.length === 1 ? "account" : "accounts"}
            </span>
          )}
        </div>
        {users.isLoading ? (
          <div className="h-32 animate-pulse bg-canvas" />
        ) : users.data?.length ? (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className={tableHead}>
                <tr>
                  <th className="px-5 py-2.5 font-semibold">Account</th>
                  <th className="px-3 py-2.5 font-semibold">Role</th>
                  <th className="px-3 py-2.5 font-semibold">Status</th>
                  <th className="px-5 py-2.5 text-right font-semibold">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {users.data.map((account) => (
                  <tr key={account.username}>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <Avatar email={account.email} size="h-8 w-8" />
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-ink">
                            {account.username}
                          </p>
                          <EmailAddress
                            email={account.email}
                            className="text-[13px] text-ink-4"
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      {account.role === "admin" ? (
                        <Pill tone="info">Admin</Pill>
                      ) : (
                        <Pill>User</Pill>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {account.active ? (
                        <Pill tone="ok">Active</Pill>
                      ) : (
                        <Pill tone="bad">Disabled</Pill>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            update.reset();
                            setResetUsername(account.username);
                            setReplacementPassword("");
                          }}
                          disabled={update.isPending || operationsBlocked}
                          className={buttonSmall}
                        >
                          Reset password
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            update.mutate({
                              name: account.username,
                              payload: {
                                role:
                                  account.role === "admin" ? "user" : "admin",
                              },
                            })
                          }
                          disabled={update.isPending || operationsBlocked}
                          className={buttonSmall}
                        >
                          Make {account.role === "admin" ? "user" : "admin"}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            update.mutate({
                              name: account.username,
                              payload: { active: !account.active },
                            })
                          }
                          disabled={update.isPending || operationsBlocked}
                          className={buttonSmall}
                        >
                          {account.active ? "Disable" : "Enable"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="p-6 text-center text-sm text-ink-4">
            No local users yet.
          </p>
        )}
      </section>

      <form onSubmit={submit} className={`overflow-hidden ${card}`}>
        <div className={cardHeader}>
          <div>
            <h2 className={`${cardTitle} flex items-center gap-2`}>
              <UserPlus size={17} aria-hidden="true" /> Add local user
            </h2>
            <p className="mt-0.5 text-[13px] text-ink-4">
              Creates a separate username and password for this portal.
            </p>
          </div>
        </div>
        <div className="grid gap-3.5 p-5 md:grid-cols-2">
          <label className={fieldLabel}>
            <span>Username</span>
            <input
              className={fieldInput}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="off"
              minLength={3}
              required
            />
          </label>
          <label className={fieldLabel}>
            <span>Email</span>
            <input
              className={fieldInput}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              required
            />
          </label>
          <label className={fieldLabel}>
            <span>Temporary password</span>
            <input
              className={fieldInput}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 10 characters"
              type="password"
              autoComplete="new-password"
              minLength={10}
              maxLength={256}
              required
            />
          </label>
          <label className={fieldLabel}>
            <span>Portal role</span>
            <select
              className={fieldInput}
              value={role}
              onChange={(e) => setRole(e.target.value as "user" | "admin")}
            >
              <option value="user">User — own API access only</option>
              <option value="admin">Admin — full management access</option>
            </select>
          </label>
          <div className="md:col-span-2">
            <button
              disabled={
                create.isPending || update.isPending || operationsBlocked
              }
              className={buttonPrimary}
            >
              {create.isPending
                ? "Adding..."
                : operationsBlocked
                  ? "Account actions paused"
                  : "Add user"}
            </button>
          </div>
        </div>
      </form>

      {resetUsername && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !update.isPending)
              closeReset();
          }}
        >
          <form
            ref={dialogRef}
            onSubmit={submitPasswordReset}
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-password-title"
            className="flex max-h-[90vh] w-full max-w-md flex-col gap-4 overflow-y-auto rounded-2xl border border-line bg-card p-6 shadow-2xl"
          >
            <div>
              <h3
                id="reset-password-title"
                className="text-lg font-bold text-ink"
              >
                Reset {resetUsername}&apos;s password
              </h3>
              <p className="mt-1 text-[13px] text-ink-4">
                Their current password stops working as soon as this change
                succeeds.
              </p>
            </div>
            <label className={fieldLabel}>
              <span>New password</span>
              <input
                className={fieldInput}
                type="password"
                autoComplete="new-password"
                minLength={10}
                maxLength={256}
                required
                value={replacementPassword}
                onChange={(event) => setReplacementPassword(event.target.value)}
              />
            </label>
            {update.error && (
              <p role="alert" className="text-sm text-danger">
                {update.error.message}
              </p>
            )}
            {operationsBlocked && (
              <p role="alert" className="text-sm text-sand-ink">
                Account actions are paused. Try again in {retryAfter || 1}{" "}
                seconds.
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                disabled={update.isPending}
                onClick={closeReset}
                className={buttonSecondary}
              >
                Cancel
              </button>
              <button
                disabled={
                  update.isPending ||
                  operationsBlocked ||
                  replacementPassword.length < 10 ||
                  replacementPassword.length > 256
                }
                className={buttonPrimary}
              >
                {update.isPending ? "Saving..." : "Reset password"}
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
