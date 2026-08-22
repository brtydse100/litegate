import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, KeyRound, Search, ShieldAlert, UserRound, X } from "lucide-react";
import { api } from "../api/client";
import { useDialogDismiss } from "../hooks/useDialogDismiss";
import type { TeamInfo, TeamMember } from "../types";

const fieldClass = "w-full rounded-lg border border-[#2A2E42] bg-[#0F1117] px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none";

export default function TeamMembersDialog({ team, pending, operationsBlocked, error, onClose, onMove }: {
  team: TeamInfo;
  pending: boolean;
  operationsBlocked: boolean;
  error?: string;
  onClose: () => void;
  onMove: (userId: string, destinationTeamId: string) => void;
}) {
  useDialogDismiss(onClose, pending);
  const [selected, setSelected] = useState<TeamMember | null>(null);
  const [destinationId, setDestinationId] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const protectedTeam = team.mapped_groups.length > 0 || team.default_key_team;
  const destinations = useQuery({
    queryKey: ["team-move-destinations", search],
    queryFn: () => api.listTeams(1, 100, search),
  });
  const options = (destinations.data?.teams ?? []).filter(item => item.team_id !== team.team_id);
  const members = team.members_with_roles ?? [];

  function chooseMember(member: TeamMember) {
    setSelected(member);
    setDestinationId("");
    setAcknowledged(false);
  }

  function applySearch(event: React.FormEvent) {
    event.preventDefault();
    setSearch(searchInput.trim());
  }

  return <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="team-members-title" onMouseDown={event => { if (event.target === event.currentTarget && !pending) onClose(); }}>
    <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-[#2A2E42] bg-[#1A1D27] p-5 shadow-2xl">
      <div className="flex items-start justify-between gap-4">
        <div><h3 id="team-members-title" className="text-lg font-semibold text-white">Members of {team.team_alias || team.team_id}</h3><p className="mt-1 font-mono text-[11px] text-gray-600">{team.team_id}</p></div>
        <button onClick={onClose} aria-label="Close team members" className="rounded p-1 text-gray-500 hover:bg-[#22263A] hover:text-white"><X size={18} /></button>
      </div>

      {protectedTeam && <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs leading-5 text-amber-100/70"><ShieldAlert size={14} className="mr-1 inline" />Members cannot be moved out while this team is referenced by SSO mapping or <code>KEY_TEAM_ID</code>; the configuration would assign them back.</div>}

      <div className="mt-4 overflow-hidden rounded-xl border border-[#2A2E42]">
        {members.length ? members.map((member, index) => <div key={member.user_id || member.user_email || index} className="flex flex-col gap-3 border-b border-[#2A2E42] p-3 last:border-b-0 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-3"><div className="rounded-lg bg-cyan-500/10 p-2 text-cyan-300"><UserRound size={16} /></div><div className="min-w-0"><p className="truncate text-sm text-gray-200">{member.user_email || member.user_id || "Unknown member"}</p>{member.user_email && member.user_id && <p className="truncate font-mono text-[10px] text-gray-600">{member.user_id}</p>}</div><span className="rounded bg-[#22263A] px-2 py-0.5 text-[10px] text-gray-400">{member.role}</span></div>
          <button onClick={() => chooseMember(member)} disabled={protectedTeam || operationsBlocked || !member.user_id} title={!member.user_id ? "A stable LiteLLM user ID is required" : protectedTeam ? "Change the team mapping/default configuration first" : operationsBlocked ? "Wait for the operation cooldown" : "Move member"} className="flex items-center justify-center gap-1.5 rounded-lg border border-[#2A2E42] px-3 py-2 text-xs text-gray-300 hover:bg-[#22263A] disabled:cursor-not-allowed disabled:opacity-35">Move <ArrowRight size={13} /></button>
        </div>) : <p className="p-8 text-center text-sm text-gray-500">This team has no members yet.</p>}
      </div>

      {selected?.user_id && <div className="mt-5 rounded-xl border border-indigo-500/25 bg-indigo-500/5 p-4">
        <h4 className="text-sm font-semibold text-white">Move {selected.user_email || selected.user_id}</h4>
        <p className="mt-1 text-xs leading-5 text-gray-400">LiteGate adds the destination membership, moves every API key scoped to this source team, verifies the key updates, and only then removes the source membership.</p>
        <form onSubmit={applySearch} className="mt-4 flex gap-2"><input aria-label="Search destination teams" className={fieldClass} value={searchInput} onChange={event => setSearchInput(event.target.value)} placeholder="Filter destination teams" /><button className="flex items-center gap-1.5 rounded-lg border border-[#2A2E42] px-3 py-2 text-xs text-gray-300"><Search size={13} /> Search</button></form>
        <label className="mt-3 block space-y-1 text-xs text-gray-400"><span>Destination team</span><select className={fieldClass} value={destinationId} onChange={event => setDestinationId(event.target.value)}><option value="">Select a destination</option>{options.map(option => <option key={option.team_id} value={option.team_id}>{option.team_alias || option.team_id} — {option.team_id}</option>)}</select></label>
        {destinations.isFetching && <p className="mt-2 text-[11px] text-gray-600">Refreshing destinations...</p>}
        {destinations.error && <p className="mt-2 text-xs text-red-300">{(destinations.error as Error).message}</p>}
        <label className="mt-4 flex items-start gap-2 text-xs leading-5 text-gray-300"><input className="mt-1" type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} /><span><KeyRound size={13} className="mr-1 inline" />I understand the user's moved keys will immediately inherit the destination team's models, limits, and budget policy.</span></label>
        {error && <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>}
        <div className="mt-4 flex justify-end gap-2"><button onClick={() => setSelected(null)} className="rounded-lg border border-[#2A2E42] px-4 py-2 text-sm text-gray-300">Cancel</button><button onClick={() => onMove(selected.user_id!, destinationId)} disabled={pending || operationsBlocked || !destinationId || !acknowledged} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40">{pending ? "Moving safely..." : operationsBlocked ? "Team actions paused" : "Move user and keys"}</button></div>
      </div>}
    </div>
  </div>;
}
