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


def upsert_result(conn, resolve: TeamResolver, m, source: str, fetched_at: datetime) -> int:
    """Insert or update a finished match from a historical source; returns match id."""
    home, away = resolve(source, m.home_team), resolve(source, m.away_team)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO matches (competition_code, season, home_team_id, away_team_id, played_on, status,
                                 home_goals, away_goals, home_shots, away_shots,
                                 home_shots_on_target, away_shots_on_target, result_source, result_fetched_at)
            VALUES (%s, %s, %s, %s, %s, 'FINISHED', %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (competition_code, season, home_team_id, away_team_id) DO UPDATE SET
                played_on = EXCLUDED.played_on, status = 'FINISHED',
                home_goals = EXCLUDED.home_goals, away_goals = EXCLUDED.away_goals,
                home_shots = EXCLUDED.home_shots, away_shots = EXCLUDED.away_shots,
                home_shots_on_target = EXCLUDED.home_shots_on_target,
                away_shots_on_target = EXCLUDED.away_shots_on_target,
                result_source = EXCLUDED.result_source, result_fetched_at = EXCLUDED.result_fetched_at
            RETURNING id
            """,
            (m.competition_code, m.season, home, away, m.played_on, m.home_goals, m.away_goals,
             m.home_shots, m.away_shots, m.home_shots_on_target, m.away_shots_on_target, source, fetched_at),
        )
        match_id = cur.fetchone()[0]
        if m.closing_odds:
            cur.execute(
                "INSERT INTO match_odds (match_id, source, kind, home, draw, away, fetched_at) "
                "VALUES (%s, %s, 'closing', %s, %s, %s, %s) ON CONFLICT (match_id, source, kind) DO UPDATE SET "
                "home = EXCLUDED.home, draw = EXCLUDED.draw, away = EXCLUDED.away, fetched_at = EXCLUDED.fetched_at",
                (match_id, f"{source}:{m.closing_odds_source}", *m.closing_odds, fetched_at),
            )
    return match_id


def upsert_fixture(conn, resolve: TeamResolver, f, season: str) -> int:
    """Insert or update a fixture from the fixtures API; returns match id.

    A result already recorded from another source is never overwritten with NULLs.
    """
    home, away = resolve(f.source, f.home_team), resolve(f.source, f.away_team)
    with conn.cursor() as cur:
        cur.execute(
            """
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
            RETURNING id
            """,
            dict(c=f.competition_code, s=season, h=home, a=away, d=f.kickoff_utc.date(), k=f.kickoff_utc,
                 st=f.status, hg=f.home_goals, ag=f.away_goals, src=f.source, sid=f.source_match_id,
                 fa=f.fetched_at),
        )
        return cur.fetchone()[0]


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
    """mk: MatchMarkets (full) or an object with home_win/draw/away_win only."""
    over = getattr(mk, "over", {}) or {}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO predictions (match_id, model_run_id, p_home, p_draw, p_away, exp_home_goals, exp_away_goals,
                                     p_over_1_5, p_over_2_5, p_over_3_5, p_btts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (match_id, run_id, mk.home_win, mk.draw, mk.away_win,
             getattr(mk, "expected_home_goals", None), getattr(mk, "expected_away_goals", None),
             over.get(1.5), over.get(2.5), over.get(3.5), getattr(mk, "btts_yes", None)),
        )
