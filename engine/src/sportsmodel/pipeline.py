"""End-to-end run: ingest -> store -> walk-forward backtest -> evaluate -> live forecasts -> export.

    DATABASE_URL=... FOOTBALL_DATA_ORG_TOKEN=... uv run python -m sportsmodel.pipeline
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from . import competitions, db
from .backtest import MODEL_VERSION, Forecast, MatchRecord, Run, Settings, market_forecast, walk_forward
from .discover_teams import current_season_start
from .evaluate import report as make_report
from .providers import football_data_csv as csvsrc
from .providers.base import ProviderError
from .providers.football_data_org import FootballDataOrg
from .teams import CSV, csv_only_aliases, historical_only_aliases, load_mapping

UPCOMING = {"SCHEDULED", "TIMED"}
# Forecasts are only made for matches starting at least this long after the run starts: a run takes
# minutes, and the database rejects any live forecast stored at or after kick-off.
MIN_LEAD = timedelta(hours=2)
MODEL_CONFIG = Path(__file__).resolve().parents[2] / "data" / "model_config.json"


def load_settings(path: Path = MODEL_CONFIG) -> Settings:
    """Hyper-parameters chosen on the validation period (see tune.py)."""
    if not path.exists():
        return Settings()
    cfg = json.loads(path.read_text())
    return Settings(**cfg["settings"])


def log(msg: str) -> None:
    print(msg, flush=True)


def current_season(comp: str, today: date) -> str:
    c = competitions.get(comp)
    return str(today.year) if c.calendar_season else competitions.season_for(comp, current_season_start(today))


def ingest(conn, comps: list[str], seasons: int, api: FootballDataOrg | None) -> dict:
    today = date.today()
    start = current_season_start(today)
    fetched_at = db.now()
    history: dict[tuple[str, str], list] = {}
    problems: list[str] = []
    for comp in comps:
        c = competitions.get(comp)
        if c.kind == "csv_extra":
            first = (today.year if c.calendar_season else start) - seasons + 1
            try:
                rows = csvsrc.extra_results(comp, first)
            except ProviderError as e:
                problems.append(f"{comp}: {e}")
                continue
            for r in rows:
                history.setdefault((comp, r.season), []).append(r)
            continue
        for y in range(start - seasons + 1, start + 1):
            s = competitions.season_for(comp, y)
            try:
                history[(comp, s)] = csvsrc.results(comp, s)
            except ProviderError as e:
                problems.append(f"{comp} {s}: {e}")

    csv_comps = [c for c in comps if competitions.get(c).kind != "api"]
    api_comps = [c for c in comps if competitions.get(c).kind == "api"]
    csv_fixtures = []
    if csv_comps:
        try:
            csv_fixtures = csvsrc.upcoming_fixtures(csv_comps, fetched_at)
        except ProviderError as e:
            problems.append(f"upcoming fixtures: {e}")

    # team identities: API leagues are mapped by hand, CSV-only leagues keep their CSV names
    api_names_by_season: dict[str, set[str]] = defaultdict(set)
    names_by_comp: dict[str, set[str]] = defaultdict(set)
    for (comp, s), rows in history.items():
        for r in rows:
            names_by_comp[comp].update((r.home_team, r.away_team))
            if comp in api_comps:
                api_names_by_season[s].update((r.home_team, r.away_team))
    for f in csv_fixtures:
        names_by_comp[f.competition_code].update((f.home_team, f.away_team))
    mapping = load_mapping()
    current_api = competitions.season_for("PL", start)
    aliases = mapping + historical_only_aliases(api_names_by_season, current_api, mapping)
    aliases += csv_only_aliases({c: n for c, n in names_by_comp.items() if c in csv_comps},
                                {c: n for c, n in names_by_comp.items() if c in api_comps}, mapping)
    db.load_aliases(conn, aliases)
    resolve = db.TeamResolver(conn)

    stored = dict(((c, s), n) for c, s, n in conn.execute(
        "SELECT competition_code, season, count(*) FROM matches WHERE result_source = %s GROUP BY 1, 2", (CSV,)))
    skipped = []
    for (comp, s), rows in sorted(history.items()):
        if s != current_season(comp, today) and stored.get((comp, s)) == len(rows):
            skipped.append(f"{comp} {s}")  # finished season already stored in full
            continue
        db.upsert_results(conn, resolve, rows, CSV, fetched_at)
    conn.commit()

    fixture_counts: dict[str, int] = defaultdict(int)
    fixture_dates: dict[str, list[str]] = {}
    for f in csv_fixtures:
        d = f.kickoff_utc.isoformat()[:16]
        lo, hi = fixture_dates.get(f.competition_code, [d, d])
        fixture_dates[f.competition_code] = [min(lo, d), max(hi, d)]
    for comp in api_comps:
        fixtures = api.season_matches(comp, start)
        db.upsert_fixtures(conn, resolve, fixtures, current_api)
        fixture_counts[comp] = len(fixtures)
    by_season: dict[str, list] = defaultdict(list)
    for f in csv_fixtures:
        by_season[competitions.season_of_date(f.competition_code, f.leg_date)].append(f)
        fixture_counts[f.competition_code] += 1
    for season, fs in by_season.items():
        db.upsert_fixtures(conn, resolve, fs, season)
    conn.commit()
    return {"csv_seasons": {f"{c} {s}": len(r) for (c, s), r in sorted(history.items())},
            "fixtures": dict(fixture_counts), "csv_fixture_kickoffs_utc": fixture_dates, "problems": problems, "unchanged_seasons_skipped": len(skipped),
            "fetched_at": fetched_at.isoformat()}


def load_records(conn, comp: str, now: datetime, horizon_days: int = 14) -> list[MatchRecord]:
    rows = conn.execute(
        """
        SELECT m.id, m.played_on, m.kickoff_utc, m.status, th.name, ta.name, m.home_goals, m.away_goals,
               o.home, o.draw, o.away
        FROM matches m
        JOIN teams th ON th.id = m.home_team_id
        JOIN teams ta ON ta.id = m.away_team_id
        LEFT JOIN LATERAL (SELECT home, draw, away FROM match_odds
                           WHERE match_id = m.id AND kind = 'closing' ORDER BY source LIMIT 1) o ON true
        WHERE m.competition_code = %s
        """, (comp,)).fetchall()
    out = []
    for mid, played_on, kickoff, status, home, away, hg, ag, oh, od, oa in rows:
        if hg is None and not (status in UPCOMING and kickoff and now + MIN_LEAD < kickoff <= now + timedelta(days=horizon_days)):
            continue  # postponed / in play / too far ahead: neither a result nor a fixture to forecast now
        out.append(MatchRecord(mid, comp, played_on, home, away, hg, ag,
                               (float(oh), float(od), float(oa)) if oh is not None else None))
    return out


def store(conn, forecasts: list[Forecast], mode: str, cutoff_ts=None) -> None:
    run_ids = {}
    for f in forecasts:
        if id(f.run) not in run_ids:
            ts = cutoff_ts or datetime.combine(f.run.cutoff, time.min, tzinfo=timezone.utc)
            run_ids[id(f.run)] = db.create_model_run(conn, f.run.model, MODEL_VERSION, mode, f.match.competition,
                                                     ts, f.run.n_train, f.run.params)
    db.insert_predictions(conn, ((f.match.key, run_ids[id(f.run)], f.probs) for f in forecasts))
    conn.commit()


def fmt(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def markdown(rep: dict, ingest_info: dict, live: list[Forecast], test_from: date) -> str:
    lines = [f"## Backtest (walk-forward, all finished matches since {test_from})", "",
             "Lower is better for log loss, Brier and RPS. The market row uses closing odds (known only at kickoff) "
             "and is a benchmark, not a model.", ""]
    for comp, models in rep.items():
        lines += [f"### {comp}", "", "| Model | n | Log loss | Brier | RPS | Accuracy | ECE | Over 2.5 Brier | BTTS Brier |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for model, m in models.items():
            lines.append(f"| {model} | {m['n']} | {fmt(m['log_loss'])} | {fmt(m['brier'])} | {fmt(m['rps'], 4)} | "
                         f"{m['accuracy']:.1%} | {fmt(m['ece_1x2'])} | "
                         f"{fmt(m.get('over_2_5', {}).get('brier'))} | {fmt(m.get('btts', {}).get('brier'))} |")
        lines.append("")
    lines += ["## Upcoming matches (Dixon–Coles estimate)", "",
              "| Kick-off date | Competition | Match | Home | Draw | Away | Exp. goals |", "|---|---|---|---|---|---|---|"]
    for f in sorted((f for f in live if f.run.model == "dixon_coles"), key=lambda f: f.match.played_on):
        p = f.probs
        lines.append(f"| {f.match.played_on} | {f.match.competition} | {f.match.home} – {f.match.away} | "
                     f"{p.home_win:.0%} | {p.draw:.0%} | {p.away_win:.0%} | "
                     f"{p.expected_home_goals:.2f} – {p.expected_away_goals:.2f} |")
    if ingest_info["problems"]:
        lines += ["", "## Data problems", ""] + [f"- {p}" for p in ingest_info["problems"]]
    return "\n".join(lines) + "\n"


def export_live(live: list[Forecast], now: datetime) -> list[dict]:
    by_match = defaultdict(dict)
    meta = {}
    for f in live:
        p = f.probs
        d = {"home": p.home_win, "draw": p.draw, "away": p.away_win, "model_cutoff": now.isoformat(),
             "n_train": f.run.n_train}
        if hasattr(p, "over"):
            d.update(expected_goals=[p.expected_home_goals, p.expected_away_goals],
                     over={str(k): v for k, v in p.over.items()}, btts=p.btts_yes,
                     most_likely_score=list(p.most_likely_score))
        by_match[f.match.key][f.run.model] = d
        meta[f.match.key] = {"match_id": f.match.key, "competition": f.match.competition,
                             "date": f.match.played_on.isoformat(), "home": f.match.home, "away": f.match.away}
    return [{**meta[k], "models": v} for k, v in by_match.items()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--competitions", default=",".join(competitions.ALL_CODES))
    ap.add_argument("--seasons", type=int, default=8, help="seasons of history to download")
    ap.add_argument("--test-from", default="2023-07-01", help="first date of the backtest")
    ap.add_argument("--horizon-days", type=int, default=14, help="forecast fixtures up to this many days ahead")
    ap.add_argument("--skip-backtest", action="store_true",
                    help="only ingest and forecast upcoming matches; reuse the last stored evaluation")
    ap.add_argument("--out", default="export")
    args = ap.parse_args(argv)
    comps = args.competitions.split(",")
    test_from = date.fromisoformat(args.test_from)

    conn = db.connect()
    db.migrate(conn)
    db.seed_competitions(conn)
    try:
        api = FootballDataOrg() if any(competitions.get(c).kind == "api" for c in comps) else None
        info = ingest(conn, comps, args.seasons, api)
    except (ProviderError, ValueError) as e:
        print(f"ERROR during ingestion: {e}", file=sys.stderr)
        return 1
    log(f"Ingested: {json.dumps(info, indent=1)}")

    settings = load_settings()
    log(f"Settings: {settings}")
    now = db.now()
    all_bt, all_live, all_mkt = [], [], []
    for comp in comps:
        recs = load_records(conn, comp, now, args.horizon_days)
        # with --skip-backtest the walk-forward starts after the last finished match, so it only forecasts
        start = now.date() + timedelta(days=1) if args.skip_backtest else test_from
        bt, live = walk_forward(recs, start, settings, live_cutoff=now.date())
        mkt_run = Run("market_closing", test_from, 0, {"method": "proportional"})
        mkt = [] if args.skip_backtest else [Forecast(mkt_run, m, p) for m in recs
                                             if m.finished and m.played_on >= test_from and (p := market_forecast(m))]
        if not args.skip_backtest:
            # keep one backtest per model version, so a persistent database does not grow on every run
            conn.execute("DELETE FROM model_runs WHERE mode = 'backtest' AND model_version = %s "
                         "AND competition_code = %s", (MODEL_VERSION, comp))
            store(conn, bt, "backtest")
        store(conn, live, "live", cutoff_ts=now)
        log(f"{comp}: {len(recs)} matches, {len(bt) // 3} backtested, {len(live) // 3} upcoming forecast, "
            f"{len(mkt)} with closing odds")
        all_bt += bt
        all_live += live
        all_mkt += mkt

    if args.skip_backtest:
        row = conn.execute("SELECT report FROM evaluation_reports WHERE model_version = %s "
                           "ORDER BY created_at DESC LIMIT 1", (MODEL_VERSION,)).fetchone()
        rep = row[0] if row else {}
        log("Backtest skipped; " + ("reusing the last stored evaluation" if row else
                                    "no stored evaluation for this model version yet"))
    else:
        rep = make_report(all_bt, all_mkt)
        conn.execute("INSERT INTO evaluation_reports (model_version, test_from, report) VALUES (%s, %s, %s)",
                     (MODEL_VERSION, test_from, Jsonb(rep)))
        conn.commit()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(markdown(rep, info, all_live, test_from))
    (out / "latest.json").write_text(json.dumps({
        "generated_at": now.isoformat(), "model_version": MODEL_VERSION,
        "sources": {"results": "football-data.co.uk", "fixtures": "football-data.org"},
        "ingest": info, "evaluation": rep, "upcoming": export_live(all_live, now)}, indent=1, default=str))
    log(f"Wrote {out / 'report.md'} and {out / 'latest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
