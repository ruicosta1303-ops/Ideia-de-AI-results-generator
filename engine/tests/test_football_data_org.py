"""Parsing tests. The payload below is a hand-written example of the API's
response *shape* (test-only, not real match data)."""
from datetime import datetime, timezone

import pytest

from sportsmodel.providers.base import ProviderError
from sportsmodel.providers.football_data_org import FootballDataOrg, parse_matches

FETCHED = datetime(2026, 1, 1, tzinfo=timezone.utc)
PAYLOAD = {
    "matches": [
        {
            "id": 1,
            "utcDate": "2026-01-03T15:00:00Z",
            "status": "TIMED",
            "matchday": 20,
            "lastUpdated": "2026-01-01T08:00:00Z",
            "competition": {"code": "XX", "name": "Example League"},
            "homeTeam": {"name": "Example Home FC"},
            "awayTeam": {"name": "Example Away FC"},
            "score": {"fullTime": {"home": None, "away": None}},
        },
        {
            "id": 2,
            "utcDate": "2025-12-28T20:00:00Z",
            "status": "FINISHED",
            "competition": {"code": "XX", "name": "Example League"},
            "homeTeam": {"name": "B"},
            "awayTeam": {"name": "C"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        },
    ]
}


def test_parses_scheduled_and_finished_matches():
    upcoming, finished = parse_matches(PAYLOAD, FETCHED)
    assert upcoming.kickoff_utc == datetime(2026, 1, 3, 15, tzinfo=timezone.utc)
    assert upcoming.home_goals is None and upcoming.away_goals is None
    assert upcoming.source == "football-data.org" and upcoming.fetched_at == FETCHED
    assert (finished.home_goals, finished.away_goals) == (2, 1)
    assert finished.matchday is None and finished.source_last_updated is None


def test_missing_token_fails_clearly(monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_ORG_TOKEN", raising=False)
    with pytest.raises(ProviderError, match="FOOTBALL_DATA_ORG_TOKEN is not set"):
        FootballDataOrg()


def test_json_output_is_serialisable():
    import json

    json.dumps([f.to_json() for f in parse_matches(PAYLOAD, FETCHED)])
