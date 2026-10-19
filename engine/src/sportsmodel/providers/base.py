"""Provider-neutral records. Every adapter converts its own format into these."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class Fixture:
    source: str
    source_match_id: str
    competition_code: str
    competition_name: str
    kickoff_utc: datetime
    status: str  # SCHEDULED, TIMED, IN_PLAY, PAUSED, FINISHED, POSTPONED, ...
    home_team: str
    away_team: str
    home_goals: int | None  # None until the match has a score
    away_goals: int | None
    matchday: int | None
    source_last_updated: datetime | None
    fetched_at: datetime
    leg_date: date | None = None  # match date as published by the source (CSV-only leagues)

    def to_json(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, (datetime, date)):
                d[k] = v.isoformat()
        return d


class ProviderError(RuntimeError):
    pass


class FixtureProvider(Protocol):
    name: str

    def fixtures(self, competitions: list[str], date_from: date, date_to: date) -> list[Fixture]: ...
