import { Suspense } from "react";
import { pct } from "@/lib/analysis";
import { DatabaseNotConfigured } from "@/lib/db";
import { getCompetitions, getLatestEvaluation } from "@/lib/queries";
import { CalibrationChart } from "@/components/CalibrationChart";
import { LocalTime } from "@/components/LocalTime";
import { Notice, Panel } from "@/components/Panel";

export default function Page() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Model performance</h1>
        <p className="mt-1 max-w-3xl text-sm text-secondary">
          Every forecast below was made <em>before</em> the match, using only earlier results (walk-forward testing), and
          every finished league match in the test period is included — none are filtered out. Lower log loss, Brier and RPS
          are better.
        </p>
      </div>
      <Suspense fallback={<p className="text-sm text-muted">Loading evaluation…</p>}>
        <Evaluation />
      </Suspense>
    </div>
  );
}

const ORDER = ["dixon_coles", "elo", "base_rate", "market_closing (benchmark)"];
const LABEL: Record<string, string> = {
  dixon_coles: "Dixon–Coles",
  elo: "Elo",
  base_rate: "League average",
  "market_closing (benchmark)": "Betting market (closing odds) — benchmark",
};

async function Evaluation() {
  let data;
  try {
    data = await Promise.all([getLatestEvaluation(), getCompetitions()]);
  } catch (e) {
    if (e instanceof DatabaseNotConfigured) return <Notice>The database is not configured on this server.</Notice>;
    throw e;
  }
  const [ev, comps] = data;
  if (!ev) return <Notice>No evaluation has been stored yet. It is produced by the weekly backtest.</Notice>;
  const names = Object.fromEntries(comps.map((c) => [c.code, c.name]));
  const all = ev.report.ALL;
  const leagues = Object.keys(ev.report).filter((k) => k !== "ALL").sort((a, b) => (names[a] ?? a).localeCompare(names[b] ?? b));

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted">
        Model {ev.modelVersion} · test period from {ev.testFrom} · evaluated <LocalTime iso={ev.createdAt} />
      </p>

      <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
        <Panel kind="model" title="All leagues">
          <MetricsTable models={all} />
          <p className="mt-3 text-xs text-muted">
            The market row uses bookmaker closing odds, which are only known at kick-off. It is a reference point for how good the
            models are, not something they could use. Both models beat league averages; neither beats the market, so there is no
            evidence of betting value.
          </p>
        </Panel>
        <Panel kind="model" title="Calibration (1X2, all leagues)">
          <CalibrationChart
            series={[
              { name: "Dixon–Coles", colorVar: "--home", bins: all.dixon_coles?.calibration_1x2 ?? [] },
              { name: "Elo", colorVar: "--away", bins: all.elo?.calibration_1x2 ?? [] },
            ]}
          />
          <details className="mt-2 text-xs text-secondary">
            <summary className="cursor-pointer">Table view</summary>
            <table className="mt-1 w-full tabular">
              <thead className="text-muted">
                <tr>
                  <th className="text-left font-normal">Bin</th>
                  <th className="text-right font-normal">D–C said</th>
                  <th className="text-right font-normal">Happened</th>
                  <th className="text-right font-normal">n</th>
                </tr>
              </thead>
              <tbody>
                {(all.dixon_coles?.calibration_1x2 ?? []).map((b) => (
                  <tr key={b.lower}>
                    <td>{pct(b.lower)}–{pct(b.upper)}</td>
                    <td className="text-right">{pct(b.mean_predicted, 1)}</td>
                    <td className="text-right">{pct(b.observed_rate, 1)}</td>
                    <td className="text-right">{b.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </Panel>
      </div>

      <Panel kind="model" title="Goals markets (Dixon–Coles, all leagues)">
        <table className="w-full max-w-xl text-sm tabular">
          <thead className="text-xs text-muted">
            <tr>
              <th className="py-1 text-left font-normal">Market</th>
              <th className="text-right font-normal">Predicted on average</th>
              <th className="text-right font-normal">Happened</th>
              <th className="text-right font-normal">Brier</th>
              <th className="text-right font-normal">Calibration error</th>
            </tr>
          </thead>
          <tbody>
            {([["Over 2.5 goals", all.dixon_coles?.over_2_5], ["Both teams score", all.dixon_coles?.btts]] as const).map(([label, mkt]) => (
              <tr key={label} className="border-t border-border">
                <td className="py-1.5 text-secondary">{label}</td>
                <td className="text-right">{pct(mkt?.mean_predicted, 1)}</td>
                <td className="text-right">{pct(mkt?.observed_rate, 1)}</td>
                <td className="text-right">{mkt?.brier.toFixed(3) ?? "–"}</td>
                <td className="text-right">{pct(mkt?.ece, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <h2 className="pt-2 text-base font-semibold">By league</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        {leagues.map((code) => (
          <Panel key={code} kind="model" title={names[code] ?? code}>
            <MetricsTable models={ev.report[code]} />
          </Panel>
        ))}
      </div>
    </div>
  );
}

function MetricsTable({ models }: { models: Record<string, import("@/lib/types").ModelMetrics> }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm tabular">
        <thead className="text-xs text-muted">
          <tr>
            <th className="py-1 text-left font-normal">Model</th>
            <th className="text-right font-normal">Matches</th>
            <th className="text-right font-normal">Log loss</th>
            <th className="text-right font-normal">Brier</th>
            <th className="text-right font-normal">RPS</th>
            <th className="text-right font-normal">Most likely right</th>
            <th className="text-right font-normal">Calib. error</th>
          </tr>
        </thead>
        <tbody>
          {ORDER.filter((k) => models[k]).map((k) => {
            const m = models[k];
            return (
              <tr key={k} className="border-t border-border">
                <td className="py-1.5 text-secondary">{LABEL[k] ?? k}</td>
                <td className="text-right">{m.n.toLocaleString("en")}</td>
                <td className="text-right">{m.log_loss.toFixed(3)}</td>
                <td className="text-right">{m.brier.toFixed(3)}</td>
                <td className="text-right">{m.rps.toFixed(4)}</td>
                <td className="text-right">{pct(m.accuracy, 1)}</td>
                <td className="text-right">{pct(m.ece_1x2, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
