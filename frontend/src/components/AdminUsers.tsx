import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Info, Shield, UserPlus } from "lucide-react";
import { api } from "../api/client";
import { useOperationLimit } from "../hooks/useOperationLimit";

const inputClass = "rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none";

export default function AdminUsers() {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [resetUsername, setResetUsername] = useState<string | null>(null);
  const [replacementPassword, setReplacementPassword] = useState("");
  const { operationsBlocked, retryAfter, refreshOperationLimit } = useOperationLimit();

  const users = useQuery({ queryKey: ["local-users"], queryFn: api.listUsers });
  const create = useMutation({
    mutationFn: api.createUser,
    onSuccess: () => {
      setUsername(""); setEmail(""); setPassword(""); setRole("user");
      void queryClient.invalidateQueries({ queryKey: ["local-users"] });
    },
    onSettled: refreshOperationLimit,
  });
  const update = useMutation({
    mutationFn: ({ name, payload }: { name: string; payload: { active?: boolean; role?: "user" | "admin"; password?: string } }) =>
      api.updateUser(name, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["local-users"] }),
    onSettled: refreshOperationLimit,
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (operationsBlocked || create.isPending || update.isPending) return;
    create.mutate({ username, email, password, role });
  }

  function submitPasswordReset(event: React.FormEvent) {
    event.preventDefault();
    if (!resetUsername || replacementPassword.length < 10 || operationsBlocked || update.isPending) return;
    update.mutate(
      { name: resetUsername, payload: { password: replacementPassword } },
      { onSuccess: () => { setResetUsername(null); setReplacementPassword(""); } },
    );
  }

  useEffect(() => {
    if (!resetUsername) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !update.isPending) {
        setResetUsername(null);
        setReplacementPassword("");
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [resetUsername, update.isPending]);

  const error = create.error ?? update.error ?? users.error;

  return (
    <section className="w-full max-w-4xl space-y-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-indigo-400">Users</p>
        <h2 className="mt-1 text-xl font-semibold text-white">Local user access</h2>
        <p className="mt-1 text-sm text-gray-500">Manage password-based accounts for people who cannot sign in with your organization&apos;s SSO.</p>
      </div>

      <div className="grid overflow-hidden rounded-xl border border-[#2A2E42] bg-[#2A2E42] md:grid-cols-3 md:gap-px">
        <div className="bg-[#1A1D27] p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-200"><Info size={15} className="text-sky-400" /> When to use this</div>
          <p className="mt-1.5 text-xs leading-5 text-gray-500">Create a local account for contractors, emergency access, or anyone without SSO. People covered by SSO should keep using SSO.</p>
        </div>
        <div className="border-y border-[#2A2E42] bg-[#1A1D27] p-4 md:border-x md:border-y-0">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-200"><Shield size={15} className="text-indigo-400" /> User or admin?</div>
          <p className="mt-1.5 text-xs leading-5 text-gray-500"><span className="text-gray-300">Users</span> create or regenerate their own key. <span className="text-gray-300">Admins</span> manage all keys and local accounts.</p>
        </div>
        <div className="bg-[#1A1D27] p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-200"><Bot size={15} className="text-emerald-400" /> Automation agents</div>
          <p className="mt-1.5 text-xs leading-5 text-gray-500">Use the management API key for trusted agents that need admin automation. Never give an agent a shared human password.</p>
        </div>
      </div>

      {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{(error as Error).message}</p>}
      {operationsBlocked && <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">Account actions are paused. Try again in {retryAfter || 1} seconds.</p>}

      <form onSubmit={submit} className="grid gap-3 rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-5 md:grid-cols-2">
        <div className="md:col-span-2">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-200"><UserPlus size={16} /> Add local user</div>
          <p className="mt-1 text-xs text-gray-500">Creates a separate username and password for this portal.</p>
        </div>
        <label className="space-y-1 text-xs text-gray-400"><span>Username</span><input className={`${inputClass} w-full`} value={username} onChange={e => setUsername(e.target.value)} autoComplete="off" minLength={3} required /></label>
        <label className="space-y-1 text-xs text-gray-400"><span>Email</span><input className={`${inputClass} w-full`} value={email} onChange={e => setEmail(e.target.value)} type="email" required /></label>
        <label className="space-y-1 text-xs text-gray-400"><span>Temporary password</span><input className={`${inputClass} w-full`} value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 10 characters" type="password" autoComplete="new-password" minLength={10} required /></label>
        <label className="space-y-1 text-xs text-gray-400"><span>Portal role</span><select className={`${inputClass} w-full`} value={role} onChange={e => setRole(e.target.value as "user" | "admin")}>
          <option value="user">User — own API access only</option><option value="admin">Admin — full management access</option>
        </select></label>
        <button disabled={create.isPending || update.isPending || operationsBlocked} className="md:col-span-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">
          {create.isPending ? "Adding..." : operationsBlocked ? "Account actions paused" : "Add user"}
        </button>
      </form>

      <div className="overflow-hidden rounded-xl border border-[#2A2E42] bg-[#1A1D27]">
        <div className="border-b border-[#2A2E42] px-4 py-3">
          <p className="text-sm font-medium text-gray-200">Account actions</p>
          <p className="mt-1 text-xs leading-5 text-gray-500"><span className="text-gray-300">Reset password</span> replaces the current password. <span className="text-gray-300">Make admin/user</span> changes management access. <span className="text-gray-300">Disable</span> immediately blocks portal access without deleting the account.</p>
        </div>
        {users.isLoading ? <div className="h-32 animate-pulse bg-[#22263A]" /> : users.data?.length ? (
          <div className="divide-y divide-[#2A2E42]">
            {users.data.map(account => (
              <div key={account.username} className={`flex flex-col gap-3 p-4 sm:flex-row sm:items-center ${account.active ? "" : "opacity-55"}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-white">{account.username}</span>
                    {account.role === "admin" && <span className="flex items-center gap-1 rounded bg-indigo-500/15 px-1.5 py-0.5 text-[10px] text-indigo-300"><Shield size={10} /> Admin</span>}
                    {!account.active && <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] text-red-300">Disabled</span>}
                  </div>
                  <p className="truncate text-xs text-gray-500">{account.email}</p>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <button onClick={() => { setResetUsername(account.username); setReplacementPassword(""); }} disabled={update.isPending || operationsBlocked} className="rounded border border-[#2A2E42] px-2.5 py-1.5 text-gray-300 hover:bg-[#22263A] disabled:cursor-not-allowed disabled:opacity-40">Reset password</button>
                  <button onClick={() => update.mutate({ name: account.username, payload: { role: account.role === "admin" ? "user" : "admin" } })} disabled={update.isPending || operationsBlocked} className="rounded border border-[#2A2E42] px-2.5 py-1.5 text-gray-300 hover:bg-[#22263A] disabled:cursor-not-allowed disabled:opacity-40">Make {account.role === "admin" ? "user" : "admin"}</button>
                  <button onClick={() => update.mutate({ name: account.username, payload: { active: !account.active } })} disabled={update.isPending || operationsBlocked} className="rounded border border-[#2A2E42] px-2.5 py-1.5 text-gray-300 hover:bg-[#22263A] disabled:cursor-not-allowed disabled:opacity-40">{account.active ? "Disable" : "Enable"}</button>
                </div>
              </div>
            ))}
          </div>
        ) : <p className="p-6 text-center text-sm text-gray-500">No local users yet.</p>}
      </div>

      {resetUsername && <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !update.isPending) setResetUsername(null); }}>
        <form onSubmit={submitPasswordReset} role="dialog" aria-modal="true" aria-labelledby="reset-password-title" className="w-full max-w-md space-y-4 rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-5 shadow-2xl">
          <div><h3 id="reset-password-title" className="text-lg font-semibold text-white">Reset {resetUsername}&apos;s password</h3><p className="mt-1 text-xs text-gray-500">Their current password stops working as soon as this change succeeds.</p></div>
          <label className="block space-y-1 text-xs text-gray-400"><span>New password</span><input autoFocus className={`${inputClass} w-full`} type="password" autoComplete="new-password" minLength={10} required value={replacementPassword} onChange={event => setReplacementPassword(event.target.value)} /></label>
          <div className="flex justify-end gap-2"><button type="button" disabled={update.isPending} onClick={() => { setResetUsername(null); setReplacementPassword(""); }} className="rounded-lg border border-[#2A2E42] px-4 py-2 text-sm text-gray-300 disabled:opacity-40">Cancel</button><button disabled={update.isPending || operationsBlocked || replacementPassword.length < 10} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{update.isPending ? "Saving..." : "Reset password"}</button></div>
        </form>
      </div>}
    </section>
  );
}
