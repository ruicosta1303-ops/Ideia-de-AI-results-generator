import type { FormEntry } from "@/lib/analysis";

const STYLE = { W: "bg-[#1baf7a]/20 text-[#3fd09a]", D: "bg-draw/25 text-secondary", L: "bg-away/20 text-[#f08a5d]" } as const;

/** Most recent first. Outcome is shown as a letter, so it never relies on colour alone. */
export function FormStrip({ entries }: { entries: FormEntry[] }) {
  if (!entries.length) return <span className="text-sm text-muted">No recorded matches</span>;
  return (
    <ol className="flex flex-wrap gap-1" aria-label="Recent results, most recent first">
      {entries.map((e) => (
        <li
          key={e.id}
          title={`${e.playedOn} ${e.venue === "H" ? "vs" : "at"} ${e.opponent}: ${e.goalsFor}-${e.goalsAgainst}`}
          className={`flex h-6 w-6 items-center justify-center rounded text-xs font-semibold ${STYLE[e.outcome]}`}
        >
          {e.outcome}
        </li>
      ))}
    </ol>
  );
}
