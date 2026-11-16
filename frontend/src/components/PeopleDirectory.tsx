import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import EmailAddress from "./EmailAddress";

export default function PeopleDirectory() {
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const people = useQuery({
    queryKey: ["people", page, search],
    queryFn: () => api.listPeople(page, 25, search),
    retry: false,
  });
  return (
    <section
      aria-label="People directory"
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4"
    >
      <div>
        <h2 className="text-lg font-semibold text-slate-900">
          People directory
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Registered LiteLLM people, including SSO accounts and people without
          keys. This directory is read-only.
        </p>
      </div>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(draft.trim());
          setPage(1);
        }}
      >
        <label className="min-w-0 flex-1 space-y-1 text-xs text-slate-600">
          <span>Search people by email</span>
          <input
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={200}
            placeholder="Email contains..."
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900"
          />
        </label>
        <button
          type="submit"
          className="self-end rounded border border-slate-300 px-3 py-2 text-sm text-slate-700"
        >
          Search people
        </button>
      </form>
      {people.isPending && (
        <p role="status" className="text-sm text-slate-500">
          Loading people...
        </p>
      )}
      {people.error && (
        <p role="alert" className="text-sm text-red-700">
          {people.error.message}
        </p>
      )}
      {people.data && (
        <>
          <p className="text-xs text-slate-500">
            {people.data.total} people{search ? " matching email" : ""}
          </p>
          <ul className="divide-y divide-slate-200">
            {people.data.users.map((person) => (
              <li
                key={person.user_id}
                className="space-y-1 py-3 text-sm text-slate-800"
              >
                {person.email ? (
                  <EmailAddress email={person.email} />
                ) : (
                  <p>No email registered</p>
                )}
                <p className="break-all text-xs text-slate-500">
                  {person.user_id}
                </p>
                {person.upstream_role && (
                  <p className="text-xs text-slate-500">
                    LiteLLM role: {person.upstream_role}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {!people.data.users.length && (
            <p className="text-sm text-slate-500">No people found.</p>
          )}
          <div className="flex items-center gap-3 text-xs text-slate-600">
            <button
              type="button"
              aria-label="Previous people page"
              disabled={page <= 1 || people.isFetching}
              onClick={() => setPage(page - 1)}
              className="rounded border px-3 py-2 disabled:opacity-40"
            >
              Previous
            </button>
            <span>
              Page {page} of {Math.max(1, people.data.total_pages)}
            </span>
            <button
              type="button"
              aria-label="Next people page"
              disabled={page >= people.data.total_pages || people.isFetching}
              onClick={() => setPage(page + 1)}
              className="rounded border px-3 py-2 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
      )}
    </section>
  );
}
