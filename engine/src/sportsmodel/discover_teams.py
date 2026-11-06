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
    ap.add_argument("--cups", default="", help="e.g. CL: list cup teams with their country instead")
    args = ap.parse_args(argv)
    if args.cups:
        return cups(args.cups.split(","), args.seasons)
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


def cups(codes: list[str], seasons: int) -> int:
    """Teams (with country) and match stages of cup competitions, per season."""
    start = current_season_start(date.today())
    api = FootballDataOrg()
    failed = False
    for comp in codes:
        for y in range(start - seasons + 1, start + 1):
            try:
                teams = api._get(f"/competitions/{comp}/teams", {"season": y}).get("teams", [])
                matches = api._get(f"/competitions/{comp}/matches", {"season": y}).get("matches", [])
            except ProviderError as e:
                print(f"[{comp} {y}] {e}")
                failed = True
                continue
            stages: dict[str, int] = defaultdict(int)
            durations: dict[str, int] = defaultdict(int)
            for m in matches:
                stages[f"{m.get('stage')}/{m.get('status')}"] += 1
                durations[str((m.get("score") or {}).get("duration"))] += 1
            print(f"[{comp} {y}] {len(teams)} teams, {len(matches)} matches; stages: {dict(stages)}; durations: {dict(durations)}")
            print(f"CUPTEAMS {comp} {y}: " + " | ".join(
                f"{t['name']} ({(t.get('area') or {}).get('name', '?')})" for t in sorted(teams, key=lambda t: t["name"])))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
