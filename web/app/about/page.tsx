import { Panel } from "@/components/Panel";

export default function Page() {
  return (
    <div className="max-w-3xl space-y-4 text-sm leading-relaxed text-secondary">
      <h1 className="text-xl font-semibold tracking-tight text-primary">Method & data</h1>
      <Panel kind="fact" title="Data sources">
        <ul className="list-disc space-y-1 pl-5">
          <li><b className="text-primary">football-data.co.uk</b> — historical league results since 2019/20 and bookmaker closing odds. Odds are used only to benchmark the models, never as model input.</li>
          <li><b className="text-primary">football-data.org</b> — fixtures, kick-off times and current-season results.</li>
          <li>Not available (shown as “Data unavailable”): injuries, suspensions, lineups, shot-based xG, cup and European matches.</li>
          <li>Data is refreshed once a day; every page shows when it was last updated.</li>
        </ul>
      </Panel>
      <Panel kind="model" title="Models">
        <ul className="list-disc space-y-1 pl-5">
          <li><b className="text-primary">Dixon–Coles</b> (main): each team has an attack and a defence rating, plus home advantage; goals follow a Poisson distribution with a correction for low scores. Recent matches count more. Ratings of teams with few matches (e.g. promoted clubs) are pulled towards a prior. All goals markets come from one scoreline grid, so probabilities always add up to 100%.</li>
          <li><b className="text-primary">Elo</b>: one strength rating per team, updated after each match, converted to home/draw/away chances.</li>
          <li><b className="text-primary">League average</b>: the minimum any model must beat.</li>
          <li>Settings are chosen on a validation season that is not part of the reported test results.</li>
        </ul>
      </Panel>
      <Panel kind="quality" title="Honesty rules">
        <ul className="list-disc space-y-1 pl-5">
          <li>Forecasts are stored before kick-off; the database rejects any forecast that used data from after the match started.</li>
          <li>Performance is measured on every finished match, not on selected ones.</li>
          <li>The models do not beat closing betting odds in testing. Nothing here is betting advice or a promise of profit.</li>
        </ul>
      </Panel>
    </div>
  );
}
