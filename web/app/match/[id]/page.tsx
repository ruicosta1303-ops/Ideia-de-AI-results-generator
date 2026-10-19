import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import {
  binFor, disagreement, pct, PRIMARY_MODEL, restDays, staleDays, standings, summarise, teamForm, uncertainty, type FormEntry,
} from "@/lib/analysis";
import { DatabaseNotConfigured } from "@/lib/db";
import { getHeadToHead, getLatestEvaluation, getMatch, getRecentResults, getSeasonResults } from "@/lib/queries";
import type { ModelMetrics, Prediction } from "@/lib/types";
import { FormStrip } from "@/components/FormStrip";
import { LocalTime } from "@/components/LocalTime";
import { DataUnavailable, Notice, Panel } from "@/components/Panel";
import { ProbabilityBar } from "@/components/ProbabilityBar";

export default function Page({ params }: PageProps<"/match/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading match…</p>}>
      <Match params={params} />
    </Suspense>
  );
}

const MODEL_LABEL = { dixon_coles: "Dixon–Coles (main)", elo: "Elo", base_rate: "League average" } as const;

async function Match({ params }: { params: PageProps<"/match/[id]">["params"] }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) notFound();
  let m;
  try {
    m = await getMatch(id);
  } catch (e) {
    if (e instanceof DatabaseNotConfigured) return <Notice>The database is not configured on this server.</Notice>;
    throw e;
  }
  if (!m) notFound();

  const date = m.playedOn;
  const [recent, h2h, season, evaluation] = await Promise.all([
    getRecentResults([m.homeId, m.awayId], date),
    getHeadToHead(m.homeId, m.awayId, date),
    getSeasonResults(m.competition, m.season, date),
    getLatestEvaluation(),
  ]);

  const homeForm = teamForm(recent, m.homeId, 10);
  const awayForm = teamForm(recent, m.awayId, 10);
  const homeAtHome = teamForm(recent, m.homeId, 60).filter((e) => e.venue === "H").slice(0, 10);
  const awayAway = teamForm(recent, m.awayId, 60).filter((e) => e.venue === "A").slice(0, 10);
  const table = standings(season);
  const dc = m.predictions[PRIMARY_MODEL];
  const metrics = evaluation?.report?.[m.competition]?.dixon_coles ?? evaluation?.report?.ALL?.dixon_coles;
  const finished = m.homeGoals != null;
  const stale = finished ? null : staleDays(m.leagueLatestResult, m.kickoff);

  return (
    <div className="space-y-4">
      <div>
        <Link href="/" className="text-xs text-muted hover:text-secondary">← Fixtures</Link>
        <div className="mt-1 text-xs text-muted">
          {m.competitionName} · season {m.season.slice(0, 2)}/{m.season.slice(2)} · <LocalTime iso={m.kickoff ?? m.playedOn} /> · status {m.status}
        </div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          {m.home} <span className="text-muted">v</span> {m.away}
        </h1>
        {finished && (
          <p className="mt-1 text-sm">
            Final score <span className="font-semibold tabular">{m.homeGoals}–{m.awayGoals}</span>{" "}
            <span className="text-muted">(source {m.resultSource})</span>
          </p>
        )}
        <p className="mt-1 text-xs text-muted">
          Fixture source {m.fixtureSource ?? "–"}, fetched <LocalTime iso={m.fixtureFetchedAt} />
        </p>
      </div>

      {stale != null && (
        <div className="rounded-lg border border-warn/50 bg-warn/10 p-3 text-sm text-warn">
          ⚠ The latest {m.competitionName} result in our data is from {m.leagueLatestResult} ({stale} days before this match).
          Matches played since then are not in the model yet, so recent form and ratings may be out of date.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel kind="model" title="Outcome probabilities">
          {dc ? (
            <ModelBlock dc={dc} m={m} metrics={metrics} />
          ) : (
            <DataUnavailable
              what="Forecast"
              impact="No live forecast is stored for this match (it may be outside the 14-day forecast window, or already played)."
            />
          )}
        </Panel>

        <Panel kind="model" title="Model comparison">
          <table className="w-full text-sm tabular">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-1 text-left font-normal">Model</th>
                <th className="text-right font-normal">Home</th>
                <th className="text-right font-normal">Draw</th>
                <th className="text-right font-normal">Away</th>
              </tr>
            </thead>
            <tbody>
              {(["dixon_coles", "elo", "base_rate"] as const).map((k) => {
                const p = m.predictions[k];
                return (
                  <tr key={k} className="border-t border-border">
                    <td className="py-1.5 text-secondary">{MODEL_LABEL[k]}</td>
                    <td className="text-right">{pct(p?.home)}</td>
                    <td className="text-right">{pct(p?.draw)}</td>
                    <td className="text-right">{pct(p?.away)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">
            Disagreement between Dixon–Coles and Elo: {pct(disagreement(dc, m.predictions.elo) ?? undefined)} (0% = identical).
            Uncertainty of the main forecast: {dc ? pct(uncertainty(dc)) : "–"} (100% = all outcomes equally likely).
          </p>
          <p className="mt-1 text-xs text-muted">
            Both models are clearly better than league averages in testing, and both are worse than closing betting odds. See{" "}
            <Link href="/validation" className="underline">model performance</Link>.
          </p>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel kind="fact" title="Recent form (last 10, all competitions in our database)">
          <FormBlock name={m.home} entries={homeForm} matchDate={date} />
          <div className="my-3 border-t border-border" />
          <FormBlock name={m.away} entries={awayForm} matchDate={date} />
          <p className="mt-3 text-xs text-muted">
            Only league matches are in the database: cup and European games are missing, so rest days can be overstated.
          </p>
        </Panel>

        <Panel kind="fact" title="Home and away performance (last 10 at venue)">
          <VenueRow label={`${m.home} at home`} entries={homeAtHome} />
          <VenueRow label={`${m.away} away`} entries={awayAway} />
          <div className="mt-4">
            <h3 className="mb-1 text-xs font-semibold text-secondary">Head-to-head (last {h2h.length})</h3>
            {h2h.length ? (
              <ul className="space-y-0.5 text-sm tabular">
                {h2h.map((r) => (
                  <li key={r.id} className="flex justify-between gap-2">
                    <span className="text-muted">{r.playedOn}</span>
                    <span className="flex-1 truncate text-right">{r.home}</span>
                    <span className="font-semibold">{r.homeGoals}–{r.awayGoals}</span>
                    <span className="flex-1 truncate">{r.away}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No previous meetings in the database (since 2019/20).</p>
            )}
            <p className="mt-1 text-xs text-muted">
              Shown for context. Head-to-head is not given extra weight by the model: once team strength is known, small samples of past meetings add little and can mislead.
            </p>
          </div>
        </Panel>
      </div>

      <Panel kind="fact" title={`${m.competitionName} table before this match`}>
        {table.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-1 text-left font-normal">#</th>
                  <th className="text-left font-normal">Team</th>
                  <th className="text-right font-normal">P</th>
                  <th className="text-right font-normal">W</th>
                  <th className="text-right font-normal">D</th>
                  <th className="text-right font-normal">L</th>
                  <th className="text-right font-normal">GF</th>
                  <th className="text-right font-normal">GA</th>
                  <th className="text-right font-normal">Pts</th>
                </tr>
              </thead>
              <tbody>
                {table.map((r, i) => {
                  const hl = r.teamId === m.homeId || r.teamId === m.awayId;
                  return (
                    <tr key={r.teamId} className={`border-t border-border ${hl ? "bg-surface-2 font-semibold" : ""}`}>
                      <td className="py-1 text-muted">{i + 1}</td>
                      <td>{r.team}</td>
                      <td className="text-right">{r.played}</td>
                      <td className="text-right">{r.won}</td>
                      <td className="text-right">{r.drawn}</td>
                      <td className="text-right">{r.lost}</td>
                      <td className="text-right">{r.goalsFor}</td>
                      <td className="text-right">{r.goalsAgainst}</td>
                      <td className="text-right">{r.points}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">Computed from recorded results; official tables may differ (point deductions, tie-breakers).</p>
          </div>
        ) : (
          <p className="text-sm text-muted">No results recorded yet this season.</p>
        )}
      </Panel>

      <Panel kind="quality" title="What the model does not know">
        <div className="grid gap-2 sm:grid-cols-2">
          <DataUnavailable what="Injuries and suspensions" impact="No reliable licensed source is connected yet. A missing key player is not reflected in these numbers." />
          <DataUnavailable what="Expected lineups" impact="Rotation before or after European and cup matches is not taken into account." />
          <DataUnavailable what="Shot-based xG" impact="'Expected goals' above are the model's estimate from past scores, not shot-quality xG." />
          <DataUnavailable what="Cup and European fixtures" impact="Fatigue from midweek games is invisible to the model; rest days above count league games only." />
        </div>
      </Panel>

      <Panel kind="ai" title="Match report">
        <p className="text-sm text-secondary">
          Not enabled yet. When it is, an AI-written report will explain the numbers on this page — the strongest indicators, what could make the forecast wrong and what is missing. It will not create its own probabilities.
        </p>
      </Panel>
    </div>
  );
}

function ModelBlock({ dc, m, metrics }: { dc: Prediction; m: { home: string; away: string }; metrics?: ModelMetrics }) {
  const rows: [string, number | null][] = [
    ["Over 1.5 goals", dc.over15],
    ["Over 2.5 goals", dc.over25],
    ["Over 3.5 goals", dc.over35],
    ["Both teams score", dc.btts],
  ];
  const calib = metrics?.calibration_1x2 ?? [];
  return (
    <div className="space-y-4">
      <ProbabilityBar home={dc.home} draw={dc.draw} away={dc.away} homeLabel={m.home} awayLabel={m.away} />
      <div className="grid grid-cols-2 gap-3 text-sm tabular">
        <div className="rounded bg-surface-2 p-2">
          <div className="text-xs text-muted">Model expected goals</div>
          <div className="text-lg font-semibold">
            {dc.expHome?.toFixed(2) ?? "–"} <span className="text-muted">–</span> {dc.expAway?.toFixed(2) ?? "–"}
          </div>
        </div>
        <table className="text-sm">
          <tbody>
            {rows.map(([label, v]) => (
              <tr key={label}>
                <td className="py-0.5 text-secondary">{label}</td>
                <td className="text-right font-medium">{pct(v)}</td>
                <td className="pl-2 text-right text-muted">{v == null ? "" : `under ${pct(1 - v)}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {calib.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-secondary">How reliable are forecasts like these?</h3>
          <ul className="space-y-0.5 text-xs text-muted tabular">
            {([["Home win", dc.home], ["Draw", dc.draw], ["Away win", dc.away]] as const).map(([label, p]) => {
              const b = binFor(p, calib);
              return (
                <li key={label}>
                  {label} {pct(p)}: when the model said {pct(b?.lower)}–{pct(b?.upper)}, it happened{" "}
                  <span className="text-secondary">{pct(b?.observed_rate)}</span> of the time ({b?.count ?? 0} forecasts tested).
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted">
        Model {dc.version}, trained on {dc.nTrain.toLocaleString("en")} matches, data up to <time dateTime={dc.dataCutoff}>{dc.dataCutoff.slice(0, 10)}</time>.
      </p>
    </div>
  );
}

function FormBlock({ name, entries, matchDate }: { name: string; entries: FormEntry[]; matchDate: string }) {
  const s = summarise(entries);
  const rest = restDays(entries, matchDate);
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{name}</h3>
        <span className="text-xs text-muted tabular">
          {s.won}W {s.drawn}D {s.lost}L · goals {s.goalsFor}–{s.goalsAgainst} · {s.pointsPerGame?.toFixed(2) ?? "–"} pts/game ·{" "}
          {rest == null ? "rest days unknown" : `${rest} days since last recorded match`}
        </span>
      </div>
      <FormStrip entries={entries} />
    </div>
  );
}

function VenueRow({ label, entries }: { label: string; entries: FormEntry[] }) {
  const s = summarise(entries);
  return (
    <div className="mb-3">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{label}</h3>
        <span className="text-xs text-muted tabular">
          {s.played ? `${s.won}W ${s.drawn}D ${s.lost}L · scored ${(s.goalsFor / s.played).toFixed(2)}, conceded ${(s.goalsAgainst / s.played).toFixed(2)} per game` : "no matches"}
        </span>
      </div>
      <FormStrip entries={entries} />
    </div>
  );
}
