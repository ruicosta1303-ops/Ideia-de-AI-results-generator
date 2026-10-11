"""Print what is stored in the database (row counts and freshness). Never prints the URL.

    DATABASE_URL=... uv run python -m sportsmodel.db_status
"""

from __future__ import annotations

from . import db

QUERIES = {
    "matches": "SELECT count(*) FROM matches",
    "finished matches": "SELECT count(*) FROM matches WHERE home_goals IS NOT NULL",
    "closing odds": "SELECT count(*) FROM match_odds",
    "model runs (backtest)": "SELECT count(*) FROM model_runs WHERE mode = 'backtest'",
    "model runs (live)": "SELECT count(*) FROM model_runs WHERE mode = 'live'",
    "predictions": "SELECT count(*) FROM predictions",
    "evaluation reports": "SELECT count(*) FROM evaluation_reports",
    "latest result fetched": "SELECT max(result_fetched_at) FROM matches",
    "latest fixture fetched": "SELECT max(fixture_fetched_at) FROM matches",
    "database size": "SELECT pg_size_pretty(pg_database_size(current_database()))",
}


def main() -> int:
    with db.connect() as conn:
        host = conn.info.host
        print(f"Database host: {'temporary (localhost)' if host in ('localhost', '127.0.0.1') else 'permanent (remote)'}")
        for label, sql in QUERIES.items():
            print(f"  {label}: {conn.execute(sql).fetchone()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
