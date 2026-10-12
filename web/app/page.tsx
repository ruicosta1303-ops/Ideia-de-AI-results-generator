import { Suspense } from "react";
import { isSortKey, SORTS, sortFixtures, type SortKey } from "@/lib/analysis";
import { dayKey, dayLabel, GROUP_TZ } from "@/lib/dates";
import { DatabaseNotConfigured } from "@/lib/db";
import { getCompetitions, getFreshness, getUpcoming } from "@/lib/queries";
import { FixtureCard } from "@/components/FixtureCard";
import { FreshnessLine } from "@/components/Freshness";
import { Notice } from "@/components/Panel";

export default function Page({ searchParams }: PageProps<"/">) {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Upcoming fixtures</h1>
        <p className="mt-1 text-sm text-secondary">
          Today and the next 7 days. Bars show the model&apos;s estimated chances — estimates with real uncertainty, not predictions of certainty.
        </p>
      </div>
      <Suspense fallback={<p className="text-sm text-muted">Loading fixtures…</p>}>
        <Fixtures searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

function one(v: string | string[] | undefined) {
  return Array.isArray(v) ? v[0] : v;
}

async function Fixtures({ searchParams }: { searchParams: PageProps<"/">["searchParams"] }) {
  const sp = await searchParams;
  const league = one(sp.league) ?? "";
  const q = (one(sp.q) ?? "").trim();
  const sortParam = one(sp.sort);
  const sort: SortKey = isSortKey(sortParam) ? sortParam : "kickoff";

  let data;
  try {
    data = await Promise.all([getUpcoming(7), getCompetitions(), getFreshness()]);
  } catch (e) {
    if (e instanceof DatabaseNotConfigured) return <Notice>The database is not configured on this server (DATABASE_URL).</Notice>;
    throw e;
  }
  const [upcoming, competitions, freshness] = data;

  const needle = q.toLowerCase();
  const filtered = sortFixtures(
    upcoming.filter(
      (f) =>
        (!league || f.competition === league) &&
        (!needle || f.home.toLowerCase().includes(needle) || f.away.toLowerCase().includes(needle)),
    ),
    sort,
  );

  const now = new Date();
  const today = dayKey(now.toISOString());
  const tomorrow = dayKey(new Date(now.getTime() + 86_400_000).toISOString());
  const groups = new Map<string, typeof filtered>();
  if (sort === "kickoff") {
    for (const f of filtered) {
      const k = dayKey(f.kickoff ?? f.playedOn);
      groups.set(k, [...(groups.get(k) ?? []), f]);
    }
  }

  return (
    <div className="space-y-5">
      <form method="get" className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-surface-1 p-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">League</span>
          <select name="league" defaultValue={league} className="rounded border border-border bg-surface-2 px-2 py-1.5">
            <option value="">All leagues</option>
            {competitions.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Team</span>
          <input name="q" defaultValue={q} placeholder="Search team" className="w-44 rounded border border-border bg-surface-2 px-2 py-1.5" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Order by</span>
          <select name="sort" defaultValue={sort} className="rounded border border-border bg-surface-2 px-2 py-1.5">
            {Object.entries(SORTS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <button className="rounded bg-home px-3 py-1.5 font-medium text-white hover:opacity-90">Apply</button>
      </form>

      <FreshnessLine f={freshness} />

      <form action="/compare" method="get" className="space-y-5">
        {filtered.length > 0 && (
          <div className="flex items-center justify-between gap-3 text-xs text-muted">
            <span>{filtered.length} fixtures. Tick “compare” on two or more to see them side by side.</span>
            <button className="rounded border border-border bg-surface-2 px-3 py-1.5 text-sm text-primary hover:border-secondary">
              Compare selected
            </button>
          </div>
        )}
        {filtered.length === 0 && <Notice>No fixtures match these filters in the next 7 days.</Notice>}
        {sort === "kickoff" ? (
          [...groups.entries()].map(([k, list]) => (
            <section key={k}>
              <h2 className="mb-2 text-sm font-semibold text-secondary">
                {dayLabel(k, today, tomorrow)} <span className="font-normal text-muted">({list.length})</span>
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {list.map((f) => (
                  <FixtureCard key={f.id} f={f} selectable />
                ))}
              </div>
            </section>
          ))
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((f) => (
              <FixtureCard key={f.id} f={f} selectable />
            ))}
          </div>
        )}
      </form>
      <p className="text-xs text-muted">Days are grouped in {GROUP_TZ} time; kick-off times are shown in your own time zone.</p>
    </div>
  );
}
