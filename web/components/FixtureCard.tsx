import Link from "next/link";
import { pct, PRIMARY_MODEL } from "@/lib/analysis";
import type { Fixture } from "@/lib/types";
import { LocalTime } from "./LocalTime";
import { ProbabilityBar } from "./ProbabilityBar";

export function FixtureCard({ f, selectable = false }: { f: Fixture; selectable?: boolean }) {
  const p = f.predictions[PRIMARY_MODEL];
  const elo = f.predictions.elo;
  return (
    <article className="relative rounded-lg border border-border bg-surface-1 p-3 hover:border-secondary/40">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted">
        <span>{f.competitionName}</span>
        <span className="flex items-center gap-2">
          <LocalTime iso={f.kickoff} mode="time" />
          {selectable && (
            <label className="relative z-10 flex items-center gap-1 text-secondary">
              <input type="checkbox" name="ids" value={f.id} className="accent-home" /> compare
            </label>
          )}
        </span>
      </div>
      <Link href={`/match/${f.id}`} className="after:absolute after:inset-0">
        <div className="mb-2 flex justify-between gap-2 text-sm font-medium">
          <span>{f.home}</span>
          <span className="text-muted">v</span>
          <span className="text-right">{f.away}</span>
        </div>
      </Link>
      {p ? (
        <>
          <ProbabilityBar home={p.home} draw={p.draw} away={p.away} compact />
          <div className="mt-2 flex flex-wrap justify-between gap-x-3 text-xs text-muted tabular">
            <span>
              Exp. goals {p.expHome?.toFixed(2)}–{p.expAway?.toFixed(2)}
            </span>
            <span>Over 2.5 {pct(p.over25)}</span>
            {elo && (
              <span title="Elo model, for comparison">
                Elo {pct(elo.home)}/{pct(elo.draw)}/{pct(elo.away)}
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="text-xs text-warn">Forecast not available yet for this fixture.</p>
      )}
    </article>
  );
}
