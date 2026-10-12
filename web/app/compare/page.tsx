import Link from "next/link";
import { Suspense } from "react";
import { binFor, disagreement, pct, PRIMARY_MODEL, uncertainty } from "@/lib/analysis";
import { DatabaseNotConfigured } from "@/lib/db";
import { getFixtures, getLatestEvaluation } from "@/lib/queries";
import type { Fixture } from "@/lib/types";
import { LocalTime } from "@/components/LocalTime";
import { Notice, Panel } from "@/components/Panel";
import { ProbabilityBar } from "@/components/ProbabilityBar";

export default function Page({ searchParams }: PageProps<"/compare">) {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Compare matches</h1>
        <p className="mt-1 text-sm text-secondary">Tick “compare” on two or more fixtures on the fixtures page, then press “Compare selected”.</p>
      </div>
      <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
        <Comparison searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Comparison({ searchParams }: { searchParams: PageProps<"/compare">["searchParams"] }) {
  const raw = (await searchParams).ids;
  const ids = [...new Set((Array.isArray(raw) ? raw : raw ? raw.split(",") : []).map(Number).filter((n) => Number.isInteger(n) && n > 0))].slice(0, 6);
  if (ids.length < 2) {
    return (
      <Notice>
        Select at least two fixtures to compare. <Link href="/" className="underline">Go to fixtures</Link>.
      </Notice>
    );
  }
  let data;
  try {
    data = await Promise.all([getFixtures(ids), getLatestEvaluation()]);
  } catch (e) {
    if (e instanceof DatabaseNotConfigured) return <Notice>The database is not configured on this server.</Notice>;
    throw e;
  }
  const [fixtures, ev] = data;

  const rows: { label: string; render: (f: Fixture) => React.ReactNode }[] = [
    { label: "Kick-off", render: (f) => <LocalTime iso={f.kickoff} /> },
    { label: "Competition", render: (f) => f.competitionName },
    {
      label: "Dixon–Coles 1X2",
      render: (f) => {
        const p = f.predictions[PRIMARY_MODEL];
        return p ? <ProbabilityBar home={p.home} draw={p.draw} away={p.away} compact /> : <span className="text-warn">Data unavailable</span>;
      },
    },
    {
      label: "Elo 1X2",
      render: (f) => {
        const p = f.predictions.elo;
        return p ? `${pct(p.home)} / ${pct(p.draw)} / ${pct(p.away)}` : "–";
      },
    },
    {
      label: "Model expected goals",
      render: (f) => {
        const p = f.predictions[PRIMARY_MODEL];
        return p?.expHome != null && p.expAway != null ? `${p.expHome.toFixed(2)} – ${p.expAway.toFixed(2)}` : "–";
      },
    },
    { label: "Over 2.5 goals", render: (f) => pct(f.predictions[PRIMARY_MODEL]?.over25) },
    { label: "Both teams score", render: (f) => pct(f.predictions[PRIMARY_MODEL]?.btts) },
    {
      label: "Uncertainty",
      render: (f) => {
        const p = f.predictions[PRIMARY_MODEL];
        return p ? pct(uncertainty(p)) : "–";
      },
    },
    { label: "Model disagreement", render: (f) => pct(disagreement(f.predictions[PRIMARY_MODEL], f.predictions.elo) ?? undefined) },
    {
      label: "Similar forecasts in testing",
      render: (f) => {
        const p = f.predictions[PRIMARY_MODEL];
        const bins = ev?.report?.[f.competition]?.dixon_coles?.calibration_1x2;
        if (!p || !bins) return "–";
        const fav = Math.max(p.home, p.draw, p.away);
        const b = binFor(fav, bins);
        return b ? `Favourite at ${pct(b.lower)}–${pct(b.upper)} happened ${pct(b.observed_rate)} (n=${b.count}, this league)` : "–";
      },
    },
    {
      label: "Data used",
      render: (f) => {
        const p = f.predictions[PRIMARY_MODEL];
        return p ? `${p.nTrain.toLocaleString("en")} matches up to ${p.dataCutoff.slice(0, 10)}; no injuries/lineups/xG` : "–";
      },
    },
  ];

  return (
    <Panel kind="model" title={`${fixtures.length} matches`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm tabular">
          <thead>
            <tr>
              <th className="w-40" />
              {fixtures.map((f) => (
                <th key={f.id} className="px-2 pb-2 text-left align-bottom font-semibold">
                  <Link href={`/match/${f.id}`} className="hover:underline">
                    {f.home} <span className="text-muted">v</span> {f.away}
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-border align-top">
                <th className="py-2 pr-2 text-left text-xs font-normal text-muted">{r.label}</th>
                {fixtures.map((f) => (
                  <td key={f.id} className="px-2 py-2">{r.render(f)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
