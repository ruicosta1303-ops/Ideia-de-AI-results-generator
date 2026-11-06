"""Team identity across providers.

data/team_aliases.csv maps every current-season team explicitly. Teams that only
appear in older football-data.co.uk seasons (relegated clubs) get their CSV name
as identity. A CSV name from the *current* season that is not mapped is an error,
because it would silently create a duplicate team.
"""

from __future__ import annotations

import csv
from pathlib import Path

ALIASES = Path(__file__).resolve().parents[2] / "data" / "team_aliases.csv"
CUP_TEAMS = Path(__file__).resolve().parents[2] / "data" / "cup_teams.csv"
API = "football-data.org"
CSV = "football-data.co.uk"


class TeamMappingError(ValueError):
    pass


def load_mapping(path: Path = ALIASES) -> list[tuple[str, str, str]]:
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            for source, col in ((API, "football_data_org"), (CSV, "football_data_co_uk")):
                name = r[col].strip()
                if not name:
                    continue
                if (source, name) in seen:
                    raise TeamMappingError(f"{name!r} is mapped twice for {source}")
                seen.add((source, name))
                rows.append((source, name, r["canonical"].strip()))
    return rows


def historical_only_aliases(csv_names_by_season: dict[str, set[str]], current_season: str,
                            mapping: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Aliases for CSV team names that are not mapped explicitly."""
    mapped = {n for s, n, _ in mapping if s == CSV}
    unmapped_current = sorted(csv_names_by_season.get(current_season, set()) - mapped)
    if unmapped_current:
        raise TeamMappingError(f"current-season teams missing from team_aliases.csv: {unmapped_current}")
    every = set().union(*csv_names_by_season.values()) if csv_names_by_season else set()
    canonical = {c for _, _, c in mapping}
    out = []
    for n in sorted(every - mapped):
        if n in canonical:
            raise TeamMappingError(f"historical name {n!r} collides with a canonical team name")
        out.append((CSV, n, n))
    return out


def csv_only_aliases(names_by_comp: dict[str, set[str]], other_csv_names: dict[str, set[str]],
                     mapping: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Aliases for leagues whose results and fixtures both come from football-data.co.uk.

    Every team keeps its CSV name as identity. Because aliases are keyed by name only, the
    same name in two different competitions would silently merge two clubs, so that is an
    error unless team_aliases.csv maps it explicitly.
    """
    mapped = {n for s, n, _ in mapping if s == CSV}
    canonical = {c for _, _, c in mapping}
    seen: dict[str, str] = {}
    for comp, names in {**other_csv_names, **names_by_comp}.items():
        for n in names - mapped:
            if n in seen and seen[n] != comp:
                raise TeamMappingError(f"team name {n!r} appears in both {seen[n]} and {comp}; map it in team_aliases.csv")
            seen[n] = comp
    out = []
    for comp, names in sorted(names_by_comp.items()):
        for n in sorted(names - mapped):
            if n in canonical:
                raise TeamMappingError(f"{comp} team {n!r} collides with a canonical team name")
            out.append((CSV, n, n))
    return out


def load_cup_mapping(league_mapping: list[tuple[str, str, str]], path: Path = CUP_TEAMS) -> list[tuple[str, str, str]]:
    """Aliases for cup (football-data.org) team names that the league mapping does not cover.

    data/cup_teams.csv maps a cup name to the club we already rate (its canonical name: the
    football-data.org name for the API leagues, the football-data.co.uk name for CSV-only leagues),
    or to itself for clubs from leagues we do not cover. A name already in the league mapping must
    agree with it, otherwise one club would be split in two.
    """
    league = {n: c for s, n, c in league_mapping if s == API}
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            name, canonical = r["football_data_org"].strip(), r["canonical"].strip()
            if name in seen:
                raise TeamMappingError(f"cup team {name!r} is listed twice in cup_teams.csv")
            seen.add(name)
            if name in league and league[name] != canonical:
                raise TeamMappingError(f"cup team {name!r} maps to {canonical!r} but the league mapping says {league[name]!r}")
            rows.append((API, name, canonical))
    return rows
