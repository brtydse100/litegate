import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield, UserPlus } from "lucide-react";
import { api } from "../api/client";

const inputClass = "rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-indigo-500 focus:outline-none";

export default function AdminUsers() {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");

  const users = useQuery({ queryKey: ["local-users"], queryFn: api.listUsers });
  const create = useMutation({
    mutationFn: api.createUser,
    onSuccess: () => {
      setUsername(""); setEmail(""); setPassword(""); setRole("user");
      void queryClient.invalidateQueries({ queryKey: ["local-users"] });
    },
  });
  const update = useMutation({
    mutationFn: ({ name, payload }: { name: string; payload: { active?: boolean; role?: "user" | "admin"; password?: string } }) =>
      api.updateUser(name, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["local-users"] }),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    create.mutate({ username, email, password, role });
  }

  function resetPassword(name: string) {
    const next = window.prompt(`New password for ${name} (at least 10 characters)`);
    if (next) update.mutate({ name, payload: { password: next } });
  }

  const error = create.error ?? update.error ?? users.error;

  return (
    <section className="w-full max-w-4xl space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-white">Local users</h2>
        <p className="mt-1 text-sm text-gray-500">Add people who cannot use SSO. Passwords are salted and hashed.</p>
      </div>

      {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{(error as Error).message}</p>}

      <form onSubmit={submit} className="grid gap-3 rounded-xl border border-[#2A2E42] bg-[#1A1D27] p-5 md:grid-cols-2">
        <div className="md:col-span-2 flex items-center gap-2 text-sm font-medium text-gray-200"><UserPlus size={16} /> Add local user</div>
        <input className={inputClass} value={username} onChange={e => setUsername(e.target.value)} placeholder="Username" minLength={3} required />
        <input className={inputClass} value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" type="email" required />
        <input className={inputClass} value={password} onChange={e => setPassword(e.target.value)} placeholder="Temporary password (10+ characters)" type="password" minLength={10} required />
        <select className={inputClass} value={role} onChange={e => setRole(e.target.value as "user" | "admin")}>
          <option value="user">User</option><option value="admin">Admin</option>
        </select>
        <button disabled={create.isPending} className="md:col-span-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50">
          {create.isPending ? "Adding..." : "Add user"}
        </button>
      </form>

      <div className="overflow-hidden rounded-xl border border-[#2A2E42] bg-[#1A1D27]">
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
                  <button onClick={() => resetPassword(account.username)} className="rounded border border-[#2A2E42] px-2.5 py-1.5 text-gray-300 hover:bg-[#22263A]">Reset password</button>
                  <button onClick={() => update.mutate({ name: account.username, payload: { role: account.role === "admin" ? "user" : "admin" } })} className="rounded border border-[#2A2E42] px-2.5 py-1.5 text-gray-300 hover:bg-[#22263A]">Make {account.role === "admin" ? "user" : "admin"}</button>
                  <button onClick={() => update.mutate({ name: account.username, payload: { active: !account.active } })} className="rounded border border-[#2A2E42] px-2.5 py-1.5 text-gray-300 hover:bg-[#22263A]">{account.active ? "Disable" : "Enable"}</button>
                </div>
              </div>
            ))}
          </div>
        ) : <p className="p-6 text-center text-sm text-gray-500">No local users yet.</p>}
      </div>
    </section>
  );
}
