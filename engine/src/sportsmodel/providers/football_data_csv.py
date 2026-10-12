"""Adapter for the free historical CSV files published by football-data.co.uk.

One file per league and season, e.g. https://www.football-data.co.uk/mmz4281/2526/E0.csv
Contains final scores, basic match stats and bookmaker odds. Closing odds are
kept only to benchmark the model against the market, never as model input.
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

from .base import ProviderError

BASE_URL = "https://www.football-data.co.uk/mmz4281"
SOURCE = "football-data.co.uk"

# our competition code (football-data.org codes) -> football-data.co.uk division
DIVISIONS = {"PL": "E0", "PD": "SP1", "BL1": "D1", "SA": "I1", "FL1": "F1", "PPL": "P1", "DED": "N1"}

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
        odds, odds_src = None, None
        for cols in CLOSING_ODDS:
            vals = [_float(row.get(c)) for c in cols]
            if all(vals):
                odds, odds_src = tuple(vals), cols[0][:-1]
                break
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


def download(competition_code: str, season: str, base_url: str = BASE_URL) -> str:
    url = f"{base_url}/{season}/{DIVISIONS[competition_code]}.csv"
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


def results(competition_code: str, season: str) -> list[HistoricalMatch]:
    return parse_csv(download(competition_code, season), competition_code, season)
