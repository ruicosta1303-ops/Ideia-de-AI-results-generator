"""One-off check of which competitions the configured data sources really provide.

    FOOTBALL_DATA_ORG_TOKEN=... uv run python -m sportsmodel.probe_sources
"""

from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request
from collections import Counter

from .providers.base import ProviderError
from .providers.football_data_csv import decode
from .providers.football_data_org import FootballDataOrg

CSV_BASE = "https://www.football-data.co.uk"


def get_csv(path: str) -> list[dict] | str:
    try:
        req = urllib.request.Request(f"{CSV_BASE}/{path}", headers={"User-Agent": "sportsmodel/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return list(csv.DictReader(io.StringIO(decode(r.read()))))
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return f"unreachable: {e.reason}"


def main() -> int:
    api = FootballDataOrg()
    comps = api._get("/competitions", {}).get("competitions", [])
    print("football-data.org competitions (code | name | area | plan):")
    for c in sorted(comps, key=lambda c: (c.get("plan") or "", c.get("area", {}).get("name") or "")):
        print(f"  {c.get('code')} | {c.get('name')} | {c.get('area', {}).get('name')} | {c.get('plan')}")
    europe = [c["code"] for c in comps if c.get("code") and (c.get("area", {}).get("name") == "Europe")]
    print("\nAccess test with this token (current season matches):")
    for code in europe:
        try:
            m = api._get(f"/competitions/{code}/matches", {})
            print(f"  {code}: OK, {len(m.get('matches', []))} matches, season {m.get('filters', {}).get('season')}")
        except ProviderError as e:
            print(f"  {code}: {str(e)[:160]}")

    print("\nChampions League history with this token:")
    for season in (2025, 2024, 2023, 2022):
        try:
            m = api._get("/competitions/CL/matches", {"season": season})
            done = [x for x in m.get("matches", []) if x.get("status") == "FINISHED"]
            print(f"  CL {season}: OK, {len(done)} finished matches")
        except ProviderError as e:
            print(f"  CL {season}: {str(e)[:160]}")

    print("\nfootball-data.co.uk upcoming fixtures file (fixtures.csv):")
    rows = get_csv("fixtures.csv")
    print("  ", rows if isinstance(rows, str) else dict(Counter(r.get("Div") for r in rows)))
    if not isinstance(rows, str) and rows:
        print("   columns:", ",".join(list(rows[0].keys())[:12]), "...")

    print("\nfootball-data.co.uk main-league files, season 2026/27:")
    for div in ["E1", "SC0", "B1", "T1", "G1", "D2", "I2", "SP2", "F2"]:
        r = get_csv(f"mmz4281/2627/{div}.csv")
        print(f"  {div}: {r if isinstance(r, str) else str(len(r)) + ' rows'}")

    print("\nfootball-data.co.uk extra leagues (one file per country, all seasons):")
    for code in ["AUT", "SWZ", "DNK", "NOR", "SWE", "POL", "ROU", "IRL", "FIN", "RUS"]:
        r = get_csv(f"new/{code}.csv")
        if isinstance(r, str):
            print(f"  {code}: {r}")
        else:
            seasons = sorted({x.get("Season") for x in r if x.get("Season")})
            print(f"  {code}: {len(r)} rows, seasons {seasons[:1]}..{seasons[-1:]}, league {r[-1].get('League')}, "
                  f"last date {r[-1].get('Date')}, closing odds cols: {[k for k in r[0] if k.startswith(('PSC', 'AvgC'))]}")
    extra = get_csv("new_league_fixtures.csv")
    print("\nextra leagues upcoming fixtures:", extra if isinstance(extra, str) else dict(Counter(x.get("Country") for x in extra)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
