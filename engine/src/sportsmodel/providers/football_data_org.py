"""Adapter for the football-data.org v4 REST API.

The token is read from the FOOTBALL_DATA_ORG_TOKEN environment variable on the
server (or GitHub Actions secret). It is sent only as the X-Auth-Token header
and is never logged or included in error messages.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .base import Fixture, ProviderError

BASE_URL = "https://api.football-data.org/v4"
TOKEN_ENV = "FOOTBALL_DATA_ORG_TOKEN"
MAX_RANGE_DAYS = 10  # the API rejects wider dateFrom/dateTo windows
MIN_SECONDS_BETWEEN_CALLS = 6.5  # free tier: 10 requests per minute
MAX_RATE_LIMIT_RETRIES = 3


def rate_limit_wait(body: str, reset_header: str | None) -> float:
    """Seconds to wait after HTTP 429: the server's counter reset, else 'Wait N seconds', else 60."""
    if reset_header and reset_header.strip().isdigit():
        return float(reset_header) + 1
    m = re.search(r"[Ww]ait (\d+) second", body)
    return float(m.group(1)) + 1 if m else 60.0


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_matches(payload: dict, fetched_at: datetime) -> list[Fixture]:
    fixtures = []
    for m in payload.get("matches", []):
        full_time = (m.get("score") or {}).get("fullTime") or {}
        comp = m.get("competition") or {}
        fixtures.append(
            Fixture(
                source="football-data.org",
                source_match_id=str(m["id"]),
                competition_code=comp.get("code") or "",
                competition_name=comp.get("name") or "",
                kickoff_utc=_parse_dt(m["utcDate"]),
                status=m.get("status") or "UNKNOWN",
                home_team=(m.get("homeTeam") or {}).get("name") or "",
                away_team=(m.get("awayTeam") or {}).get("name") or "",
                home_goals=full_time.get("home"),
                away_goals=full_time.get("away"),
                matchday=m.get("matchday"),
                source_last_updated=_parse_dt(m.get("lastUpdated")),
                fetched_at=fetched_at,
            )
        )
    return fixtures


class FootballDataOrg:
    name = "football-data.org"

    def __init__(self, token: str | None = None, base_url: str = BASE_URL):
        self._token = token if token is not None else os.environ.get(TOKEN_ENV, "")
        if not self._token:
            raise ProviderError(f"{TOKEN_ENV} is not set; add it as a server-side secret")
        self._base_url = base_url
        self._last_call = 0.0
        self._sleep = time.sleep

    def _get(self, path: str, params: dict) -> dict:
        wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - self._last_call)
        if self._last_call and wait > 0:
            time.sleep(wait)
        url = f"{self._base_url}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        req = urllib.request.Request(url, headers={"X-Auth-Token": self._token})
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            self._last_call = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                detail = e.read(500).decode("utf-8", "replace").replace(self._token, "***")
                if e.code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                    self._sleep(rate_limit_wait(detail, e.headers.get("X-RequestCounter-Reset")))
                    continue
                raise ProviderError(f"football-data.org returned HTTP {e.code} for {path}: {detail}") from None
            except urllib.error.URLError as e:
                raise ProviderError(f"could not reach football-data.org: {e.reason}") from None
        raise AssertionError("unreachable")

    def team_names(self, competition: str) -> list[str]:
        return sorted(t["name"] for t in self._get(f"/competitions/{competition}/teams", {}).get("teams", []))

    def season_matches(self, competition: str, season_start_year: int) -> list[Fixture]:
        """Every match of a competition season (finished, scheduled, postponed...)."""
        payload = self._get(f"/competitions/{competition}/matches", {"season": season_start_year})
        return parse_matches(payload, datetime.now(timezone.utc))

    def fixtures(self, competitions: list[str], date_from: date, date_to: date) -> list[Fixture]:
        if date_to < date_from:
            raise ValueError("date_to must not be before date_from")
        out: list[Fixture] = []
        start = date_from
        while start <= date_to:
            end = min(start + timedelta(days=MAX_RANGE_DAYS - 1), date_to)
            payload = self._get(
                "/matches",
                {"competitions": ",".join(competitions), "dateFrom": start.isoformat(), "dateTo": end.isoformat()},
            )
            out.extend(parse_matches(payload, datetime.now(timezone.utc)))
            start = end + timedelta(days=1)
        return out
