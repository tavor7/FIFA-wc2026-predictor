"""Data provider protocol for football data sources."""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class DataProvider(Protocol):
    """Interface implemented by API adapters (API-Football, football-data.org, etc.)."""

    def get_upcoming_matches(self, days_ahead: int = 14) -> list[dict[str, Any]]:
        ...

    def get_recent_matches(self, days_back: int = 14) -> list[dict[str, Any]]:
        ...

    def get_live_matches(self) -> list[dict[str, Any]]:
        ...

    def get_standings(self, league: int, season: int) -> list[dict[str, Any]]:
        ...

    def get_head_to_head(self, team1_id: int, team2_id: int) -> list[dict[str, Any]]:
        ...

    def get_fixture_events(self, fixture_id: int | str) -> list[dict[str, Any]]:
        ...

    def get_fixture_players(self, fixture_id: int | str) -> list[dict[str, Any]]:
        ...

    def get_players(self, team_id: int, season: Optional[int] = None) -> list[dict[str, Any]]:
        ...

    def get_fixture_statistics(self, fixture_id: int | str) -> list[dict[str, Any]]:
        ...

    def get_fixture_lineups(self, fixture_id: int | str) -> list[dict[str, Any]]:
        ...

    def get_injuries(
        self, team_id: Optional[int] = None, fixture_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        ...
