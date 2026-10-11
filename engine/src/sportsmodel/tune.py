"""Choose Dixon-Coles hyper-parameters on a VALIDATION period that is not used
for the final evaluation (that starts later, see pipeline --test-from).

    DATABASE_URL=... FOOTBALL_DATA_ORG_TOKEN=... uv run python -m sportsmodel.tune
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np

from . import db, metrics
from .backtest import Settings, walk_forward
from .fetch_fixtures import DEFAULT_COMPETITIONS
from .pipeline import ingest, load_records
from .providers.football_data_org import FootballDataOrg

CONFIG = Path(__file__).resolve().parents[2] / "data" / "model_config.json"


def _run(job):
    recs, valid_from, ridge = job
    bt, _ = walk_forward(recs, valid_from, Settings(dc_ridge=ridge, models=("dixon_coles",)))
    return ridge, [(f.match.outcome, f.match.home_goals + f.match.away_goals,
                    f.probs.home_win, f.probs.draw, f.probs.away_win, f.probs.over[2.5],
                    f.probs.expected_home_goals, f.probs.expected_away_goals) for f in bt]


def score(rows) -> dict:
    a = np.array(rows, dtype=float)
    o, goals, p = a[:, 0].astype(int), a[:, 1], a[:, 2:5]
    over = a[:, 5]
    _, ece = metrics.calibration(p.ravel(), np.eye(3)[o].ravel())
    two = np.stack([over, 1 - over], axis=1)
    return {"n": len(a), "log_loss": metrics.log_loss(p, o), "rps": metrics.rps(p, o), "ece_1x2": ece,
            "over_2_5_log_loss": metrics.log_loss(two, (goals <= 2.5).astype(int)),
            "share_max_prob_over_85": float((p.max(axis=1) > 0.85).mean()),
            "min_expected_goals": float(a[:, 6:8].min())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--competitions", default=",".join(DEFAULT_COMPETITIONS))
    ap.add_argument("--seasons", type=int, default=8)
    ap.add_argument("--valid-from", default="2022-07-01")
    ap.add_argument("--valid-to", default="2023-06-30")
    ap.add_argument("--grid", default="0,1,2,4,8,16")
    ap.add_argument("--out", default="export/tune.json")
    args = ap.parse_args(argv)
    valid_from, valid_to = date.fromisoformat(args.valid_from), date.fromisoformat(args.valid_to)
    comps = args.competitions.split(",")
    grid = [float(g) for g in args.grid.split(",")]

    conn = db.connect()
    db.migrate(conn)
    db.seed_competitions(conn)
    ingest(conn, comps, args.seasons, FootballDataOrg())
    now = db.now()
    data = {c: [r for r in load_records(conn, c, now) if r.finished and r.played_on <= valid_to] for c in comps}

    jobs = [(data[c], valid_from, g) for g in grid for c in comps]
    rows: dict[float, list] = {g: [] for g in grid}
    by_comp: dict[tuple, list] = {}
    with ProcessPoolExecutor() as ex:
        for (recs, _, _), (g, r) in zip(jobs, ex.map(_run, jobs)):
            rows[g] += r
            by_comp[(recs[0].competition, g)] = r

    results = {str(g): {"ALL": score(rows[g]), **{c: score(by_comp[(c, g)]) for c in comps}} for g in grid}
    best = min(grid, key=lambda g: results[str(g)]["ALL"]["log_loss"])

    print(f"Validation period {valid_from} .. {valid_to} (not part of the final test)\n")
    print("| ridge | n | log loss | RPS | ECE | over 2.5 log loss | share >85% | min exp. goals |")
    print("|---|---|---|---|---|---|---|---|")
    for g in grid:
        r = results[str(g)]["ALL"]
        print(f"| {g:g} | {r['n']} | {r['log_loss']:.4f} | {r['rps']:.4f} | {r['ece_1x2']:.4f} | "
              f"{r['over_2_5_log_loss']:.4f} | {r['share_max_prob_over_85']:.2%} | {r['min_expected_goals']:.2f} |")
    print(f"\nSELECTED dc_ridge={best:g} (lowest validation log loss)")
    for c in comps:
        print(f"  {c}: " + ", ".join(f"{g:g}->{results[str(g)][c]['log_loss']:.4f}" for g in grid))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"valid_from": args.valid_from, "valid_to": args.valid_to,
                                          "selected": {"dc_ridge": best}, "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
