import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  KeyRound,
  Search,
  ShieldAlert,
  UserRound,
  X,
} from "lucide-react";
import { api } from "../api/client";
import EmailAddress from "./EmailAddress";
import { useDialogDismiss } from "../hooks/useDialogDismiss";
import type { TeamInfo, TeamMember } from "../types";
import { fieldInput } from "./ui";

const fieldClass = fieldInput;

export default function TeamMembersDialog({
  team,
  pending,
  operationsBlocked,
  error,
  onClose,
  onMove,
}: {
  team: TeamInfo;
  pending: boolean;
  operationsBlocked: boolean;
  error?: string;
  onClose: () => void;
  onMove: (userId: string, destinationTeamId: string) => void;
}) {
  const dialogRef = useDialogDismiss(onClose, pending);
  const [selected, setSelected] = useState<TeamMember | null>(null);
  const [destinationId, setDestinationId] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const protectedTeam =
    team.organization_managed ||
    team.mapped_groups.length > 0 ||
    team.default_key_team;
  const destinations = useQuery({
    queryKey: ["team-move-destinations", search],
    queryFn: () => api.listTeams(1, 100, search),
  });
  const options = (destinations.data?.teams ?? []).filter(
    (item) => item.team_id !== team.team_id && !item.organization_managed,
  );
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

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="team-members-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onClose();
      }}
    >
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-line bg-card p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3
              id="team-members-title"
              className="text-lg font-semibold text-ink"
            >
              Members of {team.team_alias || team.team_id}
            </h3>
            <p className="mt-1 font-mono text-[11px] text-ink-4">
              {team.team_id}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close team members"
            className="rounded p-1 text-ink-4 hover:bg-canvas hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>

        {protectedTeam && (
          <div className="mt-4 rounded-lg border border-sand/40 bg-sand-tint px-3 py-2 text-xs leading-5 text-sand-ink">
            <ShieldAlert size={14} className="mr-1 inline" />
            Members cannot be moved out while this team is referenced by SSO
            mapping or <code>KEY_TEAM_ID</code>; the configuration would assign
            them back.
          </div>
        )}

        <div className="mt-4 overflow-hidden rounded-xl border border-line">
          {members.length ? (
            members.map((member, index) => (
              <div
                key={member.user_id || member.user_email || index}
                className="flex flex-col gap-3 border-b border-line p-3 last:border-b-0 sm:flex-row sm:items-center"
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <div className="rounded-lg bg-cyan-tint p-2 text-cyan-ink">
                    <UserRound size={16} />
                  </div>
                  <div className="min-w-0">
                    {member.user_email ? (
                      <EmailAddress
                        email={member.user_email}
                        className="text-sm text-ink"
                      />
                    ) : (
                      <p className="break-all text-sm text-ink">
                        {member.user_id || "Unknown member"}
                      </p>
                    )}
                    {member.user_email && member.user_id && (
                      <p className="truncate font-mono text-[10px] text-ink-4">
                        {member.user_id}
                      </p>
                    )}
                  </div>
                  <span className="rounded bg-canvas px-2 py-0.5 text-[10px] text-ink-3">
                    {member.role}
                  </span>
                </div>
                <button
                  onClick={() => chooseMember(member)}
                  disabled={
                    protectedTeam || operationsBlocked || !member.user_id
                  }
                  title={
                    !member.user_id
                      ? "A stable LiteLLM user ID is required"
                      : protectedTeam
                        ? "Change the team mapping/default configuration first"
                        : operationsBlocked
                          ? "Wait for the operation cooldown"
                          : "Move member"
                  }
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs text-ink-2 hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-35"
                >
                  Move <ArrowRight size={13} />
                </button>
              </div>
            ))
          ) : (
            <p className="p-8 text-center text-sm text-ink-4">
              This team has no members yet.
            </p>
          )}
        </div>

        {selected?.user_id && (
          <div className="mt-5 rounded-xl border border-blue/30 bg-blue-tint p-4">
            <h4 className="text-sm font-semibold text-ink">
              Move{" "}
              {selected.user_email ? (
                <EmailAddress email={selected.user_email} />
              ) : (
                selected.user_id
              )}
            </h4>
            <p className="mt-1 text-xs leading-5 text-ink-3">
              LiteGate adds the destination membership, moves every API key
              scoped to this source team, verifies the key updates, and only
              then removes the source membership.
            </p>
            <form onSubmit={applySearch} className="mt-4 flex gap-2">
              <input
                aria-label="Search destination teams"
                className={fieldClass}
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Filter destination teams"
              />
              <button className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs text-ink-2">
                <Search size={13} /> Search
              </button>
            </form>
            <label className="mt-3 block space-y-1 text-xs text-ink-3">
              <span>Destination team</span>
              <select
                className={fieldClass}
                value={destinationId}
                onChange={(event) => setDestinationId(event.target.value)}
              >
                <option value="">Select a destination</option>
                {options.map((option) => (
                  <option key={option.team_id} value={option.team_id}>
                    {option.team_alias || option.team_id} — {option.team_id}
                  </option>
                ))}
              </select>
            </label>
            {destinations.isFetching && (
              <p className="mt-2 text-[11px] text-ink-4">
                Refreshing destinations...
              </p>
            )}
            {destinations.error && (
              <p className="mt-2 text-xs text-danger">
                {(destinations.error as Error).message}
              </p>
            )}
            <label className="mt-4 flex items-start gap-2 text-xs leading-5 text-ink-2">
              <input
                className="mt-1"
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              <span>
                <KeyRound size={13} className="mr-1 inline" />I understand the
                user's moved keys will immediately inherit the destination
                team's models, limits, and budget policy.
              </span>
            </label>
            {error && (
              <p className="mt-3 rounded-lg border border-danger-line bg-danger-tint px-3 py-2 text-xs text-danger">
                {error}
              </p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setSelected(null)}
                className="rounded-lg border border-line px-4 py-2 text-sm text-ink-2"
              >
                Cancel
              </button>
              <button
                onClick={() => onMove(selected.user_id!, destinationId)}
                disabled={
                  pending ||
                  operationsBlocked ||
                  !destinationId ||
                  !acknowledged
                }
                className="rounded-lg bg-blue px-4 py-2 text-sm font-semibold text-paper hover:brightness-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {pending
                  ? "Moving safely..."
                  : operationsBlocked
                    ? "Team actions paused"
                    : "Move user and keys"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
