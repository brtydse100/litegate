import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "../api/client";
import EmailAddress from "./EmailAddress";
import { Pill } from "./Page";
import {
  buttonSecondary,
  buttonSmall,
  card,
  cardHeader,
  cardTitle,
  fieldInput,
  tableHead,
} from "./ui";

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
      className={`overflow-hidden ${card}`}
    >
      <div className={cardHeader}>
        <div>
          <h2 className={cardTitle}>People directory</h2>
          <p className="mt-0.5 text-[13px] text-ink-4">
            Registered LiteLLM people, including SSO accounts and people without
            keys. This directory is read-only.
          </p>
        </div>
        {people.data && (
          <span className="text-[13px] text-ink-4">
            {people.data.total} people{search ? " matching email" : ""}
          </span>
        )}
      </div>
      <form
        className="flex flex-wrap items-end gap-2 border-b border-line-soft px-5 py-3.5"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(draft.trim());
          setPage(1);
        }}
      >
        <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-[13px] font-semibold text-ink-2">
          <span>Search people by email</span>
          <span className="relative">
            <Search
              size={15}
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-4"
            />
            <input
              type="search"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              maxLength={200}
              placeholder="Email contains..."
              className={`${fieldInput} pl-9 font-normal`}
            />
          </span>
        </label>
        <button type="submit" className={buttonSecondary}>
          Search people
        </button>
      </form>
      {people.isPending && (
        <p role="status" className="px-5 py-4 text-sm text-ink-4">
          Loading people...
        </p>
      )}
      {people.error && (
        <p role="alert" className="px-5 py-4 text-sm text-danger">
          {people.error.message}
        </p>
      )}
      {people.data && (
        <>
          {people.data.users.length ? (
            <div className="relative overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className={tableHead}>
                  <tr>
                    <th className="px-5 py-2.5 font-semibold">Person</th>
                    <th className="px-3 py-2.5 font-semibold">User ID</th>
                    <th className="px-5 py-2.5 font-semibold">LiteLLM role</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {people.data.users.map((person) => (
                    <tr key={person.user_id}>
                      <td className="px-5 py-3 text-ink">
                        {person.email ? (
                          <EmailAddress email={person.email} />
                        ) : (
                          <p className="text-ink-4">No email registered</p>
                        )}
                      </td>
                      <td className="break-all px-3 py-3 font-mono text-[13px] text-ink-3">
                        {person.user_id}
                      </td>
                      <td className="px-5 py-3">
                        {person.upstream_role ? (
                          <Pill
                            tone={
                              person.upstream_role.includes("admin")
                                ? "info"
                                : "neutral"
                            }
                          >
                            <span className="sr-only">LiteLLM role: </span>
                            {person.upstream_role}
                          </Pill>
                        ) : (
                          <span className="text-ink-4">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="px-5 py-6 text-center text-sm text-ink-4">
              No people found.
            </p>
          )}
          <div className="flex items-center justify-between gap-3 border-t border-line-soft px-5 py-3 text-[13px] text-ink-4">
            <button
              type="button"
              aria-label="Previous people page"
              disabled={page <= 1 || people.isFetching}
              onClick={() => setPage(page - 1)}
              className={buttonSmall}
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
              className={buttonSmall}
            >
              Next
            </button>
          </div>
        </>
      )}
    </section>
  );
}
