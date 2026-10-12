"""Fetch upcoming fixtures and write them as JSON.

    uv run python -m sportsmodel.fetch_fixtures --days 7 --out fixtures.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from .providers.base import ProviderError
from .providers.football_data_org import FootballDataOrg

# Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Primeira Liga, Eredivisie
DEFAULT_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1", "PPL", "DED"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--competitions", default=",".join(DEFAULT_COMPETITIONS))
    ap.add_argument("--out", default="fixtures.json")
    args = ap.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    try:
        fixtures = FootballDataOrg().fixtures(args.competitions.split(","), today, today + timedelta(days=args.days))
    except ProviderError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    fixtures.sort(key=lambda f: f.kickoff_utc)
    with open(args.out, "w") as fh:
        json.dump([f.to_json() for f in fixtures], fh, indent=2, ensure_ascii=False)

    print(f"Fetched {len(fixtures)} fixtures from football-data.org for {today} .. {today + timedelta(days=args.days)}")
    for code, n in sorted(Counter(f.competition_code for f in fixtures).items()):
        print(f"  {code}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
