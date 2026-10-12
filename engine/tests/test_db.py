"""Integration tests against a real PostgreSQL (TEST_DATABASE_URL). Skipped if unset.
Team names and scores here are test-only examples."""
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest

from sportsmodel import db
from sportsmodel.markets import match_markets
from sportsmodel.providers.base import Fixture
from sportsmodel.providers.football_data_csv import HistoricalMatch

from tests.conftest import URL
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


def hist(goals=(2, 1), odds=(1.9, 3.4, 4.2)):
    return HistoricalMatch("PL", "2526", date(2025, 9, 1), "Home A", "Away B", *goals,
                           10, 8, 4, 3, odds, "AvgC" if odds else None)


def fixture(status="TIMED", goals=(None, None), kickoff=datetime(2025, 9, 1, 15, tzinfo=timezone.utc)):
    return Fixture("api", "123", "PL", "Premier League", kickoff, status, "Home A FC", "Away B FC",
                   *goals, 3, None, datetime(2025, 8, 30, tzinfo=timezone.utc))


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_migrations_are_idempotent(conn):
    assert db.migrate(conn) == []


def test_result_ingestion_is_idempotent(conn):
    r = db.TeamResolver(conn)
    a = db.upsert_result(conn, r, hist(), "csv", db.now())
    b = db.upsert_result(conn, r, hist(), "csv", db.now())
    assert a == b and count(conn, "matches") == 1 and count(conn, "match_odds") == 1


def test_unknown_team_fails_loudly(conn):
    bad = HistoricalMatch("PL", "2526", date(2025, 9, 1), "Nobody", "Away B", 1, 0, None, None, None, None, None, None)
    with pytest.raises(db.UnknownTeamError):
        db.upsert_result(conn, db.TeamResolver(conn), bad, "csv", db.now())


def test_fixture_and_result_from_two_sources_merge(conn):
    r = db.TeamResolver(conn)
    a = db.upsert_result(conn, r, hist(), "csv", db.now())
    b = db.upsert_fixture(conn, r, fixture(), "2526")  # fixture feed without score
    assert a == b
    row = conn.execute("SELECT home_goals, away_goals, status, kickoff_utc FROM matches").fetchone()
    assert row[:3] == (2, 1, "FINISHED") and row[3] is not None


def _run(conn, cutoff, mode="backtest"):
    return db.create_model_run(conn, "dixon_coles", "test", mode, "PL", cutoff, 100, {"xi": 0.0019})


def test_prediction_with_data_after_kickoff_is_rejected(conn):
    mid = db.upsert_fixture(conn, db.TeamResolver(conn), fixture(), "2526")
    run = _run(conn, datetime(2025, 9, 2, tzinfo=timezone.utc))
    with pytest.raises(psycopg.errors.RaiseException, match="after match"):
        db.insert_prediction(conn, mid, run, match_markets(1.4, 1.1))


def test_live_prediction_after_kickoff_is_rejected(conn):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    mid = db.upsert_fixture(conn, db.TeamResolver(conn), fixture(kickoff=past), "2526")
    run = _run(conn, past - timedelta(days=1), mode="live")
    with pytest.raises(psycopg.errors.RaiseException, match="after kickoff"):
        db.insert_prediction(conn, mid, run, match_markets(1.4, 1.1))


def test_valid_prediction_is_stored(conn):
    future = datetime.now(timezone.utc) + timedelta(days=2)
    mid = db.upsert_fixture(conn, db.TeamResolver(conn), fixture(kickoff=future), "2627")
    run = _run(conn, datetime.now(timezone.utc), mode="live")
    db.insert_prediction(conn, mid, run, match_markets(1.4, 1.1))
    p = conn.execute("SELECT p_home + p_draw + p_away, p_over_2_5 FROM predictions").fetchone()
    assert p[0] == pytest.approx(1.0) and 0 < p[1] < 1
