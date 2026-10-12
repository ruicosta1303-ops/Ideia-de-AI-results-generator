import { describe, expect, it } from "vitest";
import { binFor, disagreement, staleDays, restDays, sortFixtures, standings, summarise, teamForm, uncertainty } from "./analysis";
import type { Fixture, Result } from "./types";

// Test-only example teams and scores.
const r = (id: number, d: string, h: [number, string], a: [number, string], hg: number, ag: number): Result => ({
  id, playedOn: d, competition: "XX", homeId: h[0], home: h[1], awayId: a[0], away: a[1], homeGoals: hg, awayGoals: ag,
});
const A: [number, string] = [1, "Alpha"];
const B: [number, string] = [2, "Beta"];
const C: [number, string] = [3, "Gamma"];
const RESULTS = [
  r(1, "2026-08-01", A, B, 2, 0),
  r(2, "2026-08-08", B, C, 1, 1),
  r(3, "2026-08-15", C, A, 3, 1),
  r(4, "2026-08-22", A, C, 0, 0),
];

describe("uncertainty", () => {
  it("is 1 for a uniform forecast and lower for a confident one", () => {
    expect(uncertainty({ home: 1 / 3, draw: 1 / 3, away: 1 / 3 })).toBeCloseTo(1);
    expect(uncertainty({ home: 0.8, draw: 0.15, away: 0.05 })).toBeLessThan(0.7);
    expect(uncertainty({ home: 1, draw: 0, away: 0 })).toBe(0);
  });
});

describe("disagreement", () => {
  it("is total variation distance", () => {
    expect(disagreement({ home: 0.5, draw: 0.3, away: 0.2 }, { home: 0.4, draw: 0.3, away: 0.3 })).toBeCloseTo(0.1);
    expect(disagreement(undefined, { home: 1, draw: 0, away: 0 })).toBeNull();
  });
});

describe("standings", () => {
  it("awards points and orders by points, then goal difference", () => {
    const t = standings(RESULTS);
    expect(t.map((x) => [x.team, x.points])).toEqual([["Gamma", 5], ["Alpha", 4], ["Beta", 1]]);
    const alpha = t.find((x) => x.team === "Alpha")!;
    expect([alpha.played, alpha.won, alpha.drawn, alpha.lost, alpha.goalsFor, alpha.goalsAgainst]).toEqual([3, 1, 1, 1, 3, 3]);
  });
});

describe("form, summary and rest days", () => {
  it("lists a team's matches most recent first from its own perspective", () => {
    const f = teamForm(RESULTS, 1);
    expect(f.map((e) => `${e.venue}${e.goalsFor}-${e.goalsAgainst}${e.outcome}`)).toEqual(["H0-0D", "A1-3L", "H2-0W"]);
    expect(summarise(f)).toMatchObject({ played: 3, won: 1, drawn: 1, lost: 1, pointsPerGame: 4 / 3 });
    expect(restDays(f, "2026-08-29T15:00:00Z")).toBe(7);
    expect(restDays([], "2026-08-29")).toBeNull();
  });
});

describe("binFor", () => {
  const bins = [0, 0.5].map((lower) => ({ lower, upper: lower + 0.5, count: 1, mean_predicted: lower, observed_rate: lower }));
  it("uses half-open bins and closes the last one", () => {
    expect(binFor(0.49, bins)?.lower).toBe(0);
    expect(binFor(0.5, bins)?.lower).toBe(0.5);
    expect(binFor(1, bins)?.lower).toBe(0.5);
  });
});

describe("sortFixtures", () => {
  const fx = (id: number, kickoff: string, home: number, draw: number, away: number, goals?: number): Fixture => ({
    id, competition: "XX", competitionName: "Example", season: "2627", kickoff, playedOn: kickoff.slice(0, 10), status: "TIMED",
    homeId: id * 10, awayId: id * 10 + 1, home: `H${id}`, away: `A${id}`, fixtureSource: null, fixtureFetchedAt: null, leagueLatestResult: null,
    predictions: { dixon_coles: { home, draw, away, expHome: goals ?? null, expAway: goals ? 1 : null, over15: null, over25: null, over35: null, btts: null, createdAt: "", dataCutoff: "", nTrain: 0, version: "t" } },
  });
  const list = [
    fx(1, "2026-10-17T15:00:00Z", 0.8, 0.15, 0.05, 2),
    fx(2, "2026-10-16T15:00:00Z", 0.36, 0.3, 0.34, 0.5),
    { ...fx(3, "2026-10-15T15:00:00Z", 0, 0, 0), predictions: {} },
  ];
  it("sorts by each criterion and puts fixtures without forecasts last", () => {
    expect(sortFixtures(list, "kickoff").map((f) => f.id)).toEqual([3, 2, 1]);
    expect(sortFixtures(list, "uncertain").map((f) => f.id)).toEqual([2, 1, 3]);
    expect(sortFixtures(list, "favourite").map((f) => f.id)).toEqual([1, 2, 3]);
    expect(sortFixtures(list, "goals").map((f) => f.id)).toEqual([1, 2, 3]);
  });
});

describe("staleDays", () => {
  it("flags leagues whose latest result is 10+ days before kick-off", () => {
    expect(staleDays("2026-09-20", "2026-10-17T14:00:00Z")).toBe(27);
    expect(staleDays("2026-10-12", "2026-10-17T14:00:00Z")).toBeNull();
    expect(staleDays(null, "2026-10-17T14:00:00Z")).toBeNull();
  });
});
