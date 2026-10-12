import type { CalibrationBin, Fixture, ModelName, Result } from "./types";

export const PRIMARY_MODEL: ModelName = "dixon_coles";

/** Normalised Shannon entropy of a 1X2 forecast: 0 = certain, 1 = 1/3 each. */
export function uncertainty(p: { home: number; draw: number; away: number }): number {
  const h = [p.home, p.draw, p.away].reduce((s, x) => (x > 0 ? s - x * Math.log(x) : s), 0);
  return h / Math.log(3);
}

/** Total variation distance between two models' 1X2 forecasts (0..1). */
export function disagreement(a?: { home: number; draw: number; away: number }, b?: { home: number; draw: number; away: number }) {
  if (!a || !b) return null;
  return (Math.abs(a.home - b.home) + Math.abs(a.draw - b.draw) + Math.abs(a.away - b.away)) / 2;
}

export const SORTS = {
  kickoff: "Kick-off time",
  uncertain: "Most uncertain",
  favourite: "Clearest favourite",
  goals: "Most goals expected",
  disagreement: "Models disagree most",
} as const;
export type SortKey = keyof typeof SORTS;

export function isSortKey(s: string | undefined): s is SortKey {
  return !!s && s in SORTS;
}

/** Rank fixtures by a configurable criterion. Fixtures without a forecast go last. */
export function sortFixtures(fixtures: Fixture[], sort: SortKey): Fixture[] {
  const key = (f: Fixture): number | null => {
    const p = f.predictions[PRIMARY_MODEL];
    switch (sort) {
      case "kickoff":
        return Date.parse(f.kickoff ?? f.playedOn);
      case "uncertain":
        return p ? -uncertainty(p) : null;
      case "favourite":
        return p ? -Math.max(p.home, p.away) : null;
      case "goals":
        return p && p.expHome != null && p.expAway != null ? -(p.expHome + p.expAway) : null;
      case "disagreement": {
        const d = disagreement(p, f.predictions.elo);
        return d == null ? null : -d;
      }
    }
  };
  return [...fixtures].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    if (ka == null && kb == null) return 0;
    if (ka == null) return 1;
    if (kb == null) return -1;
    return ka - kb || Date.parse(a.kickoff ?? a.playedOn) - Date.parse(b.kickoff ?? b.playedOn);
  });
}

export interface StandingRow {
  teamId: number;
  team: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goalsFor: number;
  goalsAgainst: number;
  points: number;
}

/** League table from finished matches (3 points for a win, 1 for a draw). */
export function standings(results: Result[]): StandingRow[] {
  const rows = new Map<number, StandingRow>();
  const row = (id: number, name: string) => {
    if (!rows.has(id))
      rows.set(id, { teamId: id, team: name, played: 0, won: 0, drawn: 0, lost: 0, goalsFor: 0, goalsAgainst: 0, points: 0 });
    return rows.get(id)!;
  };
  for (const r of results) {
    const h = row(r.homeId, r.home);
    const a = row(r.awayId, r.away);
    h.played++;
    a.played++;
    h.goalsFor += r.homeGoals;
    h.goalsAgainst += r.awayGoals;
    a.goalsFor += r.awayGoals;
    a.goalsAgainst += r.homeGoals;
    if (r.homeGoals > r.awayGoals) {
      h.won++; a.lost++; h.points += 3;
    } else if (r.homeGoals < r.awayGoals) {
      a.won++; h.lost++; a.points += 3;
    } else {
      h.drawn++; a.drawn++; h.points++; a.points++;
    }
  }
  return [...rows.values()].sort(
    (x, y) =>
      y.points - x.points ||
      y.goalsFor - y.goalsAgainst - (x.goalsFor - x.goalsAgainst) ||
      y.goalsFor - x.goalsFor ||
      x.team.localeCompare(y.team),
  );
}

export interface FormEntry {
  id: number;
  playedOn: string;
  opponent: string;
  venue: "H" | "A";
  goalsFor: number;
  goalsAgainst: number;
  outcome: "W" | "D" | "L";
}

/** A team's matches, most recent first (input may be in any order). */
export function teamForm(results: Result[], teamId: number, limit = 10): FormEntry[] {
  return results
    .filter((r) => r.homeId === teamId || r.awayId === teamId)
    .sort((a, b) => Date.parse(b.playedOn) - Date.parse(a.playedOn))
    .slice(0, limit)
    .map((r) => {
      const home = r.homeId === teamId;
      const gf = home ? r.homeGoals : r.awayGoals;
      const ga = home ? r.awayGoals : r.homeGoals;
      return {
        id: r.id,
        playedOn: r.playedOn,
        opponent: home ? r.away : r.home,
        venue: home ? "H" : "A",
        goalsFor: gf,
        goalsAgainst: ga,
        outcome: gf > ga ? "W" : gf < ga ? "L" : "D",
      };
    });
}

export interface Summary {
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goalsFor: number;
  goalsAgainst: number;
  pointsPerGame: number | null;
}

export function summarise(entries: FormEntry[]): Summary {
  const s = entries.reduce(
    (acc, e) => {
      acc.played++;
      acc.goalsFor += e.goalsFor;
      acc.goalsAgainst += e.goalsAgainst;
      if (e.outcome === "W") acc.won++;
      else if (e.outcome === "D") acc.drawn++;
      else acc.lost++;
      return acc;
    },
    { played: 0, won: 0, drawn: 0, lost: 0, goalsFor: 0, goalsAgainst: 0 },
  );
  return { ...s, pointsPerGame: s.played ? (3 * s.won + s.drawn) / s.played : null };
}

/** Whole days between the team's previous recorded match and this match date. */
export function restDays(entries: FormEntry[], matchDate: string): number | null {
  if (!entries.length) return null;
  const ms = Date.parse(matchDate.slice(0, 10)) - Date.parse(entries[0].playedOn.slice(0, 10));
  return Math.round(ms / 86_400_000);
}

/** The calibration bin a probability falls into (bins are [lower, upper), last bin closed). */
export function binFor(p: number, bins: CalibrationBin[]): CalibrationBin | null {
  return (
    bins.find((b, i) => p >= b.lower && (p < b.upper || (i === bins.length - 1 && p <= b.upper))) ?? null
  );
}

export function pct(x: number | null | undefined, digits = 0): string {
  return x == null ? "–" : `${(100 * x).toFixed(digits)}%`;
}
