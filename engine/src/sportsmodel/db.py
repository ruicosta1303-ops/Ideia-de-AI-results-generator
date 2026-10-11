"""PostgreSQL access. The connection string comes from DATABASE_URL (server-side only)."""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"

COMPETITIONS = {
    "PL": ("Premier League", "E0"),
    "PD": ("Primera Division", "SP1"),
    "BL1": ("Bundesliga", "D1"),
    "SA": ("Serie A", "I1"),
    "FL1": ("Ligue 1", "F1"),
    "PPL": ("Primeira Liga", "P1"),
    "DED": ("Eredivisie", "N1"),
}


class UnknownTeamError(LookupError):
    pass


def connect(url: str | None = None) -> psycopg.Connection:
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url)


def migrate(conn: psycopg.Connection, migrations_dir: Path = MIGRATIONS) -> list[str]:
    """Apply any migration files not yet recorded; returns the versions applied."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('schema_migrations')")
        done = set()
        if cur.fetchone()[0]:
            cur.execute("SELECT version FROM schema_migrations")
            done = {r[0] for r in cur.fetchall()}
        applied = []
        for f in sorted(migrations_dir.glob("*.sql")):
            if f.stem in done:
                continue
            cur.execute(f.read_text())
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.stem,))
            applied.append(f.stem)
    conn.commit()
    return applied


def seed_competitions(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO competitions (code, name, csv_division) VALUES (%s, %s, %s) "
            "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, csv_division = EXCLUDED.csv_division",
            [(c, n, d) for c, (n, d) in COMPETITIONS.items()],
        )
    conn.commit()


def load_aliases(conn: psycopg.Connection, rows: Iterable[tuple[str, str, str]]) -> None:
    """rows: (source, source_name, canonical_name)."""
    with conn.cursor() as cur:
        for source, source_name, canonical in rows:
            cur.execute(
                "INSERT INTO teams (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                (canonical,),
            )
            team_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO team_aliases (source, source_name, team_id) VALUES (%s, %s, %s) "
                "ON CONFLICT (source, source_name) DO UPDATE SET team_id = EXCLUDED.team_id",
                (source, source_name, team_id),
            )
    conn.commit()


class TeamResolver:
    def __init__(self, conn: psycopg.Connection):
        with conn.cursor() as cur:
            cur.execute("SELECT source, source_name, team_id FROM team_aliases")
            self._map = {(s, n): t for s, n, t in cur.fetchall()}

    def __call__(self, source: str, name: str) -> int:
        try:
            return self._map[(source, name)]
        except KeyError:
            raise UnknownTeamError(f"no team alias for {name!r} from {source}; add it to team_aliases.csv") from None


def now() -> datetime:
    return datetime.now(timezone.utc)


_RESULT_SQL = """
    INSERT INTO matches (competition_code, season, home_team_id, away_team_id, played_on, status,
                         home_goals, away_goals, home_shots, away_shots,
                         home_shots_on_target, away_shots_on_target, result_source, result_fetched_at)
    VALUES (%(c)s, %(s)s, %(h)s, %(a)s, %(d)s, 'FINISHED', %(hg)s, %(ag)s, %(hs)s, %(as_)s,
            %(hst)s, %(ast)s, %(src)s, %(fa)s)
    ON CONFLICT (competition_code, season, home_team_id, away_team_id) DO UPDATE SET
        played_on = EXCLUDED.played_on, status = 'FINISHED',
        home_goals = EXCLUDED.home_goals, away_goals = EXCLUDED.away_goals,
        home_shots = EXCLUDED.home_shots, away_shots = EXCLUDED.away_shots,
        home_shots_on_target = EXCLUDED.home_shots_on_target,
        away_shots_on_target = EXCLUDED.away_shots_on_target,
        result_source = EXCLUDED.result_source, result_fetched_at = EXCLUDED.result_fetched_at
"""

_ODDS_SQL = """
    INSERT INTO match_odds (match_id, source, kind, home, draw, away, fetched_at)
    SELECT id, %(osrc)s, 'closing', %(oh)s, %(od)s, %(oa)s, %(fa)s FROM matches
    WHERE competition_code = %(c)s AND season = %(s)s AND home_team_id = %(h)s AND away_team_id = %(a)s
    ON CONFLICT (match_id, source, kind) DO UPDATE SET
        home = EXCLUDED.home, draw = EXCLUDED.draw, away = EXCLUDED.away, fetched_at = EXCLUDED.fetched_at
"""

_FIXTURE_SQL = """
    INSERT INTO matches (competition_code, season, home_team_id, away_team_id, played_on, kickoff_utc,
                         status, home_goals, away_goals, fixture_source, fixture_source_id, fixture_fetched_at,
                         result_source, result_fetched_at)
    VALUES (%(c)s, %(s)s, %(h)s, %(a)s, %(d)s, %(k)s, %(st)s, %(hg)s, %(ag)s, %(src)s, %(sid)s, %(fa)s,
            CASE WHEN %(hg)s::int IS NULL THEN NULL ELSE %(src)s END,
            CASE WHEN %(hg)s::int IS NULL THEN NULL ELSE %(fa)s::timestamptz END)
    ON CONFLICT (competition_code, season, home_team_id, away_team_id) DO UPDATE SET
        played_on = EXCLUDED.played_on, kickoff_utc = EXCLUDED.kickoff_utc,
        status = CASE WHEN matches.home_goals IS NOT NULL AND EXCLUDED.home_goals IS NULL
                      THEN matches.status ELSE EXCLUDED.status END,
        home_goals = coalesce(matches.home_goals, EXCLUDED.home_goals),
        away_goals = coalesce(matches.away_goals, EXCLUDED.away_goals),
        result_source = coalesce(matches.result_source, EXCLUDED.result_source),
        result_fetched_at = coalesce(matches.result_fetched_at, EXCLUDED.result_fetched_at),
        fixture_source = EXCLUDED.fixture_source, fixture_source_id = EXCLUDED.fixture_source_id,
        fixture_fetched_at = EXCLUDED.fixture_fetched_at
"""

_PREDICTION_SQL = """
    INSERT INTO predictions (match_id, model_run_id, p_home, p_draw, p_away, exp_home_goals, exp_away_goals,
                             p_over_1_5, p_over_2_5, p_over_3_5, p_btts)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _result_params(resolve: TeamResolver, m, source: str, fetched_at: datetime) -> dict:
    p = dict(c=m.competition_code, s=m.season, h=resolve(source, m.home_team), a=resolve(source, m.away_team),
             d=m.played_on, hg=m.home_goals, ag=m.away_goals, hs=m.home_shots, as_=m.away_shots,
             hst=m.home_shots_on_target, ast=m.away_shots_on_target, src=source, fa=fetched_at)
    if m.closing_odds:
        p.update(osrc=f"{source}:{m.closing_odds_source}", oh=m.closing_odds[0], od=m.closing_odds[1],
                 oa=m.closing_odds[2])
    return p


def _fixture_params(resolve: TeamResolver, f, season: str) -> dict:
    return dict(c=f.competition_code, s=season, h=resolve(f.source, f.home_team), a=resolve(f.source, f.away_team),
                d=f.kickoff_utc.date(), k=f.kickoff_utc, st=f.status, hg=f.home_goals, ag=f.away_goals,
                src=f.source, sid=f.source_match_id, fa=f.fetched_at)


def _prediction_params(match_id: int, run_id: int, mk) -> tuple:
    """mk: MatchMarkets (full) or an object with home_win/draw/away_win only."""
    over = getattr(mk, "over", {}) or {}
    return (match_id, run_id, mk.home_win, mk.draw, mk.away_win,
            getattr(mk, "expected_home_goals", None), getattr(mk, "expected_away_goals", None),
            over.get(1.5), over.get(2.5), over.get(3.5), getattr(mk, "btts_yes", None))


def _match_id(conn, p: dict) -> int:
    return conn.execute("SELECT id FROM matches WHERE competition_code = %(c)s AND season = %(s)s "
                        "AND home_team_id = %(h)s AND away_team_id = %(a)s", p).fetchone()[0]


def upsert_result(conn, resolve: TeamResolver, m, source: str, fetched_at: datetime) -> int:
    """Insert or update a finished match from a historical source; returns match id."""
    return upsert_results(conn, resolve, [m], source, fetched_at)[0]


def upsert_results(conn, resolve: TeamResolver, matches, source: str, fetched_at: datetime) -> list[int]:
    """Batch version (one round trip per batch, which matters for a remote database)."""
    params = [_result_params(resolve, m, source, fetched_at) for m in matches]
    with conn.cursor() as cur:
        cur.executemany(_RESULT_SQL, params)
        cur.executemany(_ODDS_SQL, [p for p in params if "osrc" in p])
    return [_match_id(conn, p) for p in params] if len(params) == 1 else []


def upsert_fixture(conn, resolve: TeamResolver, f, season: str) -> int:
    """Insert or update a fixture from the fixtures API; returns match id.

    A result already recorded from another source is never overwritten with NULLs.
    """
    p = _fixture_params(resolve, f, season)
    conn.execute(_FIXTURE_SQL, p)
    return _match_id(conn, p)


def upsert_fixtures(conn, resolve: TeamResolver, fixtures, season: str) -> None:
    with conn.cursor() as cur:
        cur.executemany(_FIXTURE_SQL, [_fixture_params(resolve, f, season) for f in fixtures])


def create_model_run(conn, model: str, version: str, mode: str, competition: str,
                     data_cutoff: datetime, n_train: int, params: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO model_runs (model, model_version, mode, competition_code, data_cutoff, n_train, params) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (model, version, mode, competition, data_cutoff, n_train, Jsonb(params)),
        )
        return cur.fetchone()[0]


def insert_prediction(conn, match_id: int, run_id: int, mk) -> None:
    conn.execute(_PREDICTION_SQL, _prediction_params(match_id, run_id, mk))


def insert_predictions(conn, items) -> None:
    """items: iterable of (match_id, run_id, markets)."""
    with conn.cursor() as cur:
        cur.executemany(_PREDICTION_SQL, [_prediction_params(*i) for i in items])
