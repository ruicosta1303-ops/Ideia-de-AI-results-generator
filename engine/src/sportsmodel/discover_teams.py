"""Print the team names each provider uses, so they can be mapped to one identity.

    uv run python -m sportsmodel.discover_teams --seasons 5
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date

from .fetch_fixtures import DEFAULT_COMPETITIONS
from .providers import football_data_csv as csvsrc
from .providers.base import ProviderError
from .providers.football_data_org import FootballDataOrg


def current_season_start(today: date) -> int:
    return today.year if today.month >= 7 else today.year - 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=5)
    args = ap.parse_args(argv)
    start = current_season_start(date.today())
    api = FootballDataOrg()
    failed = False
    for comp in DEFAULT_COMPETITIONS:
        csv_names: dict[str, set[str]] = defaultdict(set)
        for y in range(start - args.seasons + 1, start + 1):
            s = csvsrc.season_code(y)
            try:
                rows = csvsrc.results(comp, s)
            except ProviderError as e:
                print(f"[{comp} {s}] {e}")
                continue
            with_odds = sum(r.closing_odds is not None for r in rows)
            print(f"[{comp} {s}] {len(rows)} played matches, {with_odds} with closing odds, "
                  f"{rows[0].played_on if rows else '-'} .. {rows[-1].played_on if rows else '-'}")
            for r in rows:
                csv_names[r.home_team].add(s)
                csv_names[r.away_team].add(s)
        try:
            api_names = api.team_names(comp)
        except ProviderError as e:
            print(f"[{comp}] football-data.org teams: {e}")
            failed = True
            api_names = []
        print(f"CSVNAMES {comp}: " + " | ".join(f"{n} ({','.join(sorted(v))})" for n, v in sorted(csv_names.items())))
        print(f"APINAMES {comp}: " + " | ".join(api_names))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
