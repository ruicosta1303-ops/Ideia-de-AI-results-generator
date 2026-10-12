"""DEVELOPMENT ONLY: fill a local database with SYNTHETIC matches so the website can be
built and viewed without network access. Never point this at the production database.

Team names contain "Synthetic" and every source is marked SYNTHETIC; the website shows a
warning banner whenever it sees that source.

    DATABASE_URL=postgresql://localhost/sports_dev uv run python devtools/seed_synthetic.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np

from sportsmodel import db, pipeline
from sportsmodel.discover_teams import current_season_start
from sportsmodel.providers.base import Fixture
from sportsmodel.providers.football_data_csv import HistoricalMatch, season_code
from sportsmodel.teams import API, CSV

COMPS = ["PL", "PD", "PPL"]
N_TEAMS = 12
TODAY = date.today()
CURRENT = season_code(current_season_start(TODAY))
MARK = "SYNTHETIC (dev only)"


def team(comp: str, i: int) -> str:
    return f"Synthetic {comp} {i:02d}"


def strength(comp: str) -> np.ndarray:
    return np.random.default_rng(abs(hash(comp)) % 2**32).normal(0, 0.35, N_TEAMS)


def season(comp: str, code: str) -> list[HistoricalMatch]:
    rng = np.random.default_rng(int(code) * 7 + len(comp))
    s = strength(comp)
    start = date(2000 + int(code[:2]), 8, 10)
    pairs = [(h, a) for h in range(N_TEAMS) for a in range(N_TEAMS) if h != a]
    out = []
    for i, (h, a) in enumerate(pairs):
        d = start + timedelta(days=3 * (i // (N_TEAMS // 2)))
        if d >= TODAY:
            continue
        hg = rng.poisson(np.exp(0.25 + s[h] - 0.5 * s[a]))
        ag = rng.poisson(np.exp(s[a] - 0.5 * s[h]))
        odds = (round(1 / max(0.08, 0.45 + 0.3 * (s[h] - s[a])), 2), 3.4, round(1 / max(0.08, 0.3 - 0.3 * (s[h] - s[a])), 2))
        out.append(HistoricalMatch(comp, code, d, team(comp, h), team(comp, a), int(hg), int(ag), None, None, None, None,
                                   tuple(max(1.05, o) for o in odds), "AvgC"))
    return out


class FakeApi:
    def season_matches(self, comp, year):
        rows = []
        kick = datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=19)
        played = {(m.home_team, m.away_team) for m in season(comp, CURRENT)}
        free = [(h, a) for h in range(N_TEAMS) for a in range(N_TEAMS)
                if h != a and (team(comp, h), team(comp, a)) not in played]
        for i, (h, a) in enumerate(free[:12]):
            k = kick + timedelta(days=i // 3, hours=2 * (i % 3))
            rows.append(Fixture(API, f"syn-{comp}-{i}", comp, comp, k, "TIMED", team(comp, h) + " FC", team(comp, a) + " FC",
                                None, None, None, None, datetime.now(timezone.utc)))
        return rows


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if "localhost" not in url and "127.0.0.1" not in url:
        print("Refusing to seed: DATABASE_URL must point at a local database.", file=sys.stderr)
        return 1
    pipeline.FootballDataOrg = FakeApi
    pipeline.csvsrc.results = lambda comp, s: season(comp, s)
    mapping = [(src, n, team(c, i) + " FC") for c in COMPS for i in range(N_TEAMS)
               for src, n in ((API, team(c, i) + " FC"), (CSV, team(c, i)))]
    pipeline.load_mapping = lambda: mapping
    test_from = (TODAY - timedelta(days=400)).isoformat()
    rc = pipeline.main(["--competitions", ",".join(COMPS), "--seasons", "4", "--test-from", test_from,
                        "--out", "/tmp/synthetic-export"])
    with db.connect() as conn:
        conn.execute("UPDATE matches SET fixture_source = %s WHERE fixture_source IS NOT NULL", (MARK,))
        conn.execute("UPDATE matches SET result_source = %s WHERE result_source IS NOT NULL", (MARK,))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
