"""End-to-end pipeline run against a real PostgreSQL with SYNTHETIC providers
(test-only data; the real run uses football-data.co.uk and football-data.org)."""
import json
import os
from datetime import date, datetime, timedelta, timezone

import numpy as np
import psycopg
import pytest

from sportsmodel import pipeline
from sportsmodel.providers.base import Fixture
from sportsmodel.discover_teams import current_season_start
from sportsmodel.providers.football_data_csv import HistoricalMatch, season_code
from sportsmodel.teams import API, CSV
from tests.conftest import URL

pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
TEAMS = [f"Club {i}" for i in range(10)]
TODAY = date.today()
CURRENT = season_code(current_season_start(TODAY))


def synthetic_season(code: str):
    rng = np.random.default_rng(int(code))
    start = date(2000 + int(code[:2]), 8, 10)
    strength = np.linspace(-0.4, 0.4, len(TEAMS))
    out, i = [], 0
    for h in range(len(TEAMS)):
        for a in range(len(TEAMS)):
            if h == a:
                continue
            d = start + timedelta(days=3 * (i // 5))
            i += 1
            if d >= TODAY - timedelta(days=1) or (code == CURRENT and (h, a) == (0, 1)):
                continue  # not played yet (0 v 1 is the upcoming fixture)
            hg, ag = rng.poisson(np.exp(0.25 + strength[h])), rng.poisson(np.exp(strength[a]))
            out.append(HistoricalMatch("PL", code, d, TEAMS[h], TEAMS[a], int(hg), int(ag),
                                       None, None, None, None, (2.2, 3.3, 3.4), "AvgC"))
    return out


class FakeApi:
    def season_matches(self, comp, year):
        k = datetime.combine(TODAY + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15)
        return [Fixture(API, "999", comp, "Premier League", k, "TIMED", f"{TEAMS[0]} FC", f"{TEAMS[1]} FC",
                        None, None, None, None, datetime.now(timezone.utc))]


def test_full_pipeline(conn, monkeypatch, tmp_path):
    url = URL.rsplit("/", 1)[0] + "/" + conn.info.dbname  # dsn hides the password
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(pipeline, "FootballDataOrg", FakeApi)
    monkeypatch.setattr(pipeline.csvsrc, "results", lambda comp, s: synthetic_season(s))
    mapping = [(s, n, f"{t} FC") for t in TEAMS for s, n in ((API, f"{t} FC"), (CSV, t))]
    monkeypatch.setattr(pipeline, "load_mapping", lambda: mapping)

    test_from = (TODAY - timedelta(days=500)).isoformat()
    assert pipeline.main(["--competitions", "PL", "--seasons", "4", "--test-from", test_from,
                          "--out", str(tmp_path)]) == 0

    out = json.loads((tmp_path / "latest.json").read_text())
    assert len(out["upcoming"]) == 1
    up = out["upcoming"][0]
    assert set(up["models"]) == {"base_rate", "elo", "dixon_coles"}
    assert sum(up["models"]["dixon_coles"][k] for k in ("home", "draw", "away")) == pytest.approx(1)
    rep = out["evaluation"]["PL"]
    assert rep["dixon_coles"]["n"] == rep["base_rate"]["n"] == rep["market_closing (benchmark)"]["n"] > 50
    assert "Backtest" in (tmp_path / "report.md").read_text()

    with psycopg.connect(url) as c:
        live = c.execute("SELECT count(*) FROM predictions p JOIN model_runs r ON r.id = p.model_run_id "
                         "WHERE r.mode = 'live'").fetchone()[0]
        assert live == 3
        first_backtest = backtest_count(c)
        assert first_backtest > 0
    # second run is idempotent for matches
    with psycopg.connect(url) as c:
        before = c.execute("SELECT count(*) FROM matches").fetchone()[0]
    assert pipeline.main(["--competitions", "PL", "--seasons", "4", "--test-from", test_from,
                          "--out", str(tmp_path)]) == 0
    with psycopg.connect(url) as c:
        assert c.execute("SELECT count(*) FROM matches").fetchone()[0] == before
        assert backtest_count(c) == first_backtest  # replaced, not duplicated
    second = json.loads((tmp_path / "latest.json").read_text())
    assert second["ingest"]["unchanged_seasons_skipped"] == 3  # 4 seasons, the current one is always refreshed

    # daily mode: no new backtest, evaluation reused, new live forecasts added
    assert pipeline.main(["--competitions", "PL", "--seasons", "4", "--test-from", test_from,
                          "--skip-backtest", "--out", str(tmp_path)]) == 0
    with psycopg.connect(url) as c:
        assert backtest_count(c) == first_backtest
    out = json.loads((tmp_path / "latest.json").read_text())
    assert out["evaluation"]["PL"]["dixon_coles"]["n"] == rep["dixon_coles"]["n"]
    assert len(out["upcoming"]) == 1


def backtest_count(c):
    return c.execute("SELECT count(*) FROM predictions p JOIN model_runs r ON r.id = p.model_run_id "
                     "WHERE r.mode = 'backtest'").fetchone()[0]


def test_committed_model_config_loads():
    s = pipeline.load_settings()
    assert s.dc_ridge == 4.0


def test_pipeline_csv_only_league_with_repeated_meetings(conn, monkeypatch, tmp_path):
    """Austria-style league: results and fixtures from football-data.co.uk, the same pairing
    played twice per season (regular phase + split). SYNTHETIC test-only data."""
    url = URL.rsplit("/", 1)[0] + "/" + conn.info.dbname
    monkeypatch.setenv("DATABASE_URL", url)
    names = [f"Alp {i}" for i in range(8)]
    start_year = current_season_start(TODAY)

    def extra_results(comp, first_year):
        rng = np.random.default_rng(7)
        out = []
        for y in range(first_year, start_year + 1):
            season = season_code(y)
            d0 = date(y, 7, 20)
            pairs = [(h, a) for h in range(8) for a in range(8) if h != a] * 2  # every pairing twice
            for i, (h, a) in enumerate(pairs):
                d = d0 + timedelta(days=3 * (i // 4))
                if d >= TODAY - timedelta(days=1) or (y == start_year and (h, a) == (0, 1)):
                    continue
                out.append(HistoricalMatch(comp, season, d, names[h], names[a], int(rng.poisson(1.5)),
                                           int(rng.poisson(1.1)), None, None, None, None, (2.3, 3.3, 3.1), "PSC"))
        return out

    kick = datetime.combine(TODAY + timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=17)
    monkeypatch.setattr(pipeline.csvsrc, "extra_results", extra_results)
    monkeypatch.setattr(pipeline.csvsrc, "upcoming_fixtures", lambda codes, fetched: [
        Fixture("football-data.co.uk", "x", "AUT", "Austrian Bundesliga", kick, "TIMED", names[0], names[1],
                None, None, None, None, fetched, leg_date=kick.date())])
    monkeypatch.setattr(pipeline, "load_mapping", lambda: [])

    test_from = (TODAY - timedelta(days=500)).isoformat()
    assert pipeline.main(["--competitions", "AUT", "--seasons", "4", "--test-from", test_from, "--out", str(tmp_path)]) == 0
    out = json.loads((tmp_path / "latest.json").read_text())
    assert [(u["home"], u["away"]) for u in out["upcoming"]] == [("Alp 0", "Alp 1")]
    assert out["evaluation"]["AUT"]["dixon_coles"]["n"] > 100
    with psycopg.connect(url) as c:
        dup = c.execute("SELECT count(*) FROM (SELECT 1 FROM matches WHERE competition_code = 'AUT' "
                        "GROUP BY season, home_team_id, away_team_id HAVING count(*) > 1) x").fetchone()[0]
        assert dup > 0  # repeated meetings kept as separate matches
        assert c.execute("SELECT count(*) FROM matches WHERE competition_code = 'AUT' AND leg_date IS NULL").fetchone()[0] == 0
