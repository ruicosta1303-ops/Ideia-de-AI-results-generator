"""Adapter for the free CSV files published by football-data.co.uk.

* Main leagues: one file per league and season, e.g. mmz4281/2526/E0.csv
* Extra leagues: one file per country with every season, e.g. new/AUT.csv
* Upcoming rounds: fixtures.csv (main leagues) and new_league_fixtures.csv (extra leagues);
  kick-off times are UK local time.

Files contain final scores, basic match stats and bookmaker odds. Closing odds are kept
only to benchmark the model against the market, never as model input.
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .. import competitions
from .base import Fixture, ProviderError

SITE = "https://www.football-data.co.uk"
BASE_URL = f"{SITE}/mmz4281"
SOURCE = "football-data.co.uk"
UK = ZoneInfo("Europe/London")

# our competition code -> football-data.co.uk division, for leagues published as per-season files
DIVISIONS = {c.code: c.csv_code for c in competitions.COMPETITIONS.values() if c.kind in ("api", "csv_main")}

# closing 1X2 odds column sets, best first (market average, then Pinnacle, then Bet365)
CLOSING_ODDS = [("AvgCH", "AvgCD", "AvgCA"), ("PSCH", "PSCD", "PSCA"), ("B365CH", "B365CD", "B365CA")]


@dataclass(frozen=True)
class HistoricalMatch:
    competition_code: str
    season: str  # e.g. "2526"
    played_on: date
    home_team: str  # name as spelled by football-data.co.uk
    away_team: str
    home_goals: int
    away_goals: int
    home_shots: int | None
    away_shots: int | None
    home_shots_on_target: int | None
    away_shots_on_target: int | None
    closing_odds: tuple[float, float, float] | None
    closing_odds_source: str | None


def season_code(start_year: int) -> str:
    """2025 -> '2526' (season 2025/26)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def _int(v: str | None) -> int | None:
    v = (v or "").strip()
    return int(float(v)) if v else None


def _float(v: str | None) -> float | None:
    v = (v or "").strip()
    try:
        f = float(v)
    except ValueError:
        return None
    return f if f > 1.0 else None


def _date(v: str) -> date:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date {v!r}")


def decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def parse_csv(text: str, competition_code: str, season: str) -> list[HistoricalMatch]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        # files contain trailing blank lines and, for the current season, unplayed rows
        if not (row.get("HomeTeam") or "").strip() or _int(row.get("FTHG")) is None or _int(row.get("FTAG")) is None:
            continue
        odds, odds_src = _odds(row)
        out.append(
            HistoricalMatch(
                competition_code=competition_code,
                season=season,
                played_on=_date(row["Date"]),
                home_team=row["HomeTeam"].strip(),
                away_team=row["AwayTeam"].strip(),
                home_goals=_int(row["FTHG"]),
                away_goals=_int(row["FTAG"]),
                home_shots=_int(row.get("HS")),
                away_shots=_int(row.get("AS")),
                home_shots_on_target=_int(row.get("HST")),
                away_shots_on_target=_int(row.get("AST")),
                closing_odds=odds,
                closing_odds_source=odds_src,
            )
        )
    return out


def fetch(url: str) -> str:
    err = "unknown error"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sportsmodel/0.1"}), timeout=30) as r:
                return decode(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ProviderError(f"{url} not found (season not published?)") from None
            err = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            err = str(e.reason)
        time.sleep(2 ** (attempt + 1))
    raise ProviderError(f"could not download {url}: {err}")


def download(competition_code: str, season: str, base_url: str = BASE_URL) -> str:
    return fetch(f"{base_url}/{season}/{DIVISIONS[competition_code]}.csv")


def results(competition_code: str, season: str) -> list[HistoricalMatch]:
    return parse_csv(download(competition_code, season), competition_code, season)


def _odds(row: dict) -> tuple[tuple[float, float, float] | None, str | None]:
    for cols in CLOSING_ODDS:
        vals = [_float(row.get(c)) for c in cols]
        if all(vals):
            return tuple(vals), cols[0][:-1]
    return None, None


def _season_label(code: str, raw: str) -> str | None:
    """'2026/2027' -> '2627'; '2026' -> '2026' (calendar-year leagues)."""
    raw = raw.strip()
    try:
        return competitions.season_for(code, int(raw[:4]))
    except ValueError:
        return None


def parse_extra_csv(text: str, competition_code: str, min_start_year: int) -> list[HistoricalMatch]:
    """Extra-league file (all seasons): Country, League, Season, Date, Time, Home, Away, HG, AG, ..."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if not (row.get("Home") or "").strip() or _int(row.get("HG")) is None or _int(row.get("AG")) is None:
            continue
        season = _season_label(competition_code, row.get("Season") or "")
        if season is None or int((row.get("Season") or "0")[:4]) < min_start_year:
            continue
        odds, odds_src = _odds(row)
        out.append(HistoricalMatch(competition_code, season, _date(row["Date"]), row["Home"].strip(), row["Away"].strip(),
                                   _int(row["HG"]), _int(row["AG"]), None, None, None, None, odds, odds_src))
    return out


def extra_results(competition_code: str, min_start_year: int) -> list[HistoricalMatch]:
    code = competitions.get(competition_code).csv_code
    return parse_extra_csv(fetch(f"{SITE}/new/{code}.csv"), competition_code, min_start_year)


def _kickoff(d: str, t: str) -> tuple[date, datetime, bool]:
    day = _date(d)
    t = (t or "").strip()
    if t:
        hh, mm = (int(x) for x in t.split(":")[:2])
        local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=UK)
        return day, local.astimezone(timezone.utc), True
    return day, datetime(day.year, day.month, day.day, 12, tzinfo=UK).astimezone(timezone.utc), False


def parse_fixtures(text: str, wanted: dict[str, str], key_column: str, fetched_at: datetime) -> list[Fixture]:
    """Upcoming matches from fixtures.csv (key_column 'Div') or new_league_fixtures.csv ('Country').

    wanted maps the key column's value (e.g. 'B1' or 'Austria') to our competition code.
    """
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        comp = wanted.get((row.get(key_column) or "").strip())
        home = (row.get("HomeTeam") or row.get("Home") or "").strip()
        away = (row.get("AwayTeam") or row.get("Away") or "").strip()
        if not comp or not home or not away or not (row.get("Date") or "").strip():
            continue
        day, kickoff, has_time = _kickoff(row["Date"], row.get("Time") or "")
        c = competitions.get(comp)
        out.append(Fixture(SOURCE, f"{comp}:{day.isoformat()}:{home}:{away}", comp, c.name, kickoff,
                           "TIMED" if has_time else "SCHEDULED", home, away, None, None, None, None, fetched_at,
                           leg_date=day))
    return out


def upcoming_fixtures(codes: list[str], fetched_at: datetime) -> list[Fixture]:
    comps = [competitions.get(c) for c in codes]
    out: list[Fixture] = []
    main = {c.csv_code: c.code for c in comps if c.kind == "csv_main"}
    if main:
        out += parse_fixtures(fetch(f"{SITE}/fixtures.csv"), main, "Div", fetched_at)
    extra = {c.country: c.code for c in comps if c.kind == "csv_extra"}
    if extra:
        out += parse_fixtures(fetch(f"{SITE}/new_league_fixtures.csv"), extra, "Country", fetched_at)
    return out
