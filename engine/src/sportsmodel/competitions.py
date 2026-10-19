"""The competitions the engine covers and where each one's data comes from.

kind
  api        historical results from football-data.co.uk league files, fixtures and
             current-season results from the football-data.org API
  csv_main   everything from football-data.co.uk: league files (mmz4281/<season>/<code>.csv)
             and the upcoming-round file fixtures.csv
  csv_extra  everything from football-data.co.uk "extra leagues": one file per country
             (new/<code>.csv) and new_league_fixtures.csv

CSV-only leagues often have play-off / split phases in which the same home-away pairing is
played more than once per season, so their matches are identified by date as well.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Competition:
    code: str          # our identifier (football-data.org code where one exists)
    name: str
    country: str
    kind: str          # api | csv_main | csv_extra
    csv_code: str      # football-data.co.uk division (E0, B1...) or extra-league file (AUT...)
    calendar_season: bool = False  # season runs within one calendar year (e.g. Norway)

    @property
    def uses_leg_date(self) -> bool:
        return self.kind != "api"


COMPETITIONS: dict[str, Competition] = {c.code: c for c in [
    Competition("PL", "Premier League", "England", "api", "E0"),
    Competition("PD", "Primera Division", "Spain", "api", "SP1"),
    Competition("BL1", "Bundesliga", "Germany", "api", "D1"),
    Competition("SA", "Serie A", "Italy", "api", "I1"),
    Competition("FL1", "Ligue 1", "France", "api", "F1"),
    Competition("PPL", "Primeira Liga", "Portugal", "api", "P1"),
    Competition("DED", "Eredivisie", "Netherlands", "api", "N1"),
    Competition("B1", "Belgian Pro League", "Belgium", "csv_main", "B1"),
    Competition("T1", "Süper Lig", "Turkey", "csv_main", "T1"),
    Competition("G1", "Super League Greece", "Greece", "csv_main", "G1"),
    Competition("SC0", "Scottish Premiership", "Scotland", "csv_main", "SC0"),
    Competition("AUT", "Austrian Bundesliga", "Austria", "csv_extra", "AUT"),
    Competition("SWZ", "Swiss Super League", "Switzerland", "csv_extra", "SWZ"),
    Competition("DNK", "Danish Superliga", "Denmark", "csv_extra", "DNK"),
    Competition("POL", "Ekstraklasa", "Poland", "csv_extra", "POL"),
    Competition("NOR", "Eliteserien", "Norway", "csv_extra", "NOR", calendar_season=True),
    Competition("SWE", "Allsvenskan", "Sweden", "csv_extra", "SWE", calendar_season=True),
]}

API_CODES = [c.code for c in COMPETITIONS.values() if c.kind == "api"]
ALL_CODES = list(COMPETITIONS)


def get(code: str) -> Competition:
    try:
        return COMPETITIONS[code]
    except KeyError:
        raise KeyError(f"unknown competition {code!r}") from None


def season_for(code: str, start_year: int) -> str:
    """Season label: '2627' for 2026/27, '2026' for calendar-year leagues."""
    if get(code).calendar_season:
        return str(start_year)
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_of_date(code: str, d) -> str:
    if get(code).calendar_season:
        return str(d.year)
    return season_for(code, d.year if d.month >= 7 else d.year - 1)
