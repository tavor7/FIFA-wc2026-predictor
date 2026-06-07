"""API-Football provider wrapping the unified APIClient."""

from __future__ import annotations

from typing import Any, Optional

from src.api_client import APIClient


class ApiFootballProvider:
    """DataProvider implementation backed by API-Football v3 (with football-data fallback)."""

    def __init__(self, client: Optional[APIClient] = None):
        self.client = client or APIClient()

    def get_upcoming_matches(self, days_ahead: int = 14) -> list[dict[str, Any]]:
        return self.client.get_upcoming_matches(days_ahead=days_ahead)

    def get_recent_matches(self, days_back: int = 14) -> list[dict[str, Any]]:
        return self.client.get_recent_matches(days_back=days_back)

    def get_live_matches(self) -> list[dict[str, Any]]:
        return self.client.get_live_matches()

    def get_standings(self, league: int, season: int) -> list[dict[str, Any]]:
        return self.client.get_standings(league, season)

    def get_head_to_head(self, team1_id: int, team2_id: int) -> list[dict[str, Any]]:
        return self.client.get_head_to_head(team1_id, team2_id)

    def get_fixture_events(self, fixture_id: int | str) -> list[dict[str, Any]]:
        return self.client.get_fixture_events(fixture_id)

    def get_fixture_players(self, fixture_id: int | str) -> list[dict[str, Any]]:
        return self.client.get_fixture_players(fixture_id)

    def get_players(self, team_id: int, season: Optional[int] = None) -> list[dict[str, Any]]:
        return self.client.get_players(team_id, season=season)

    def get_fixture_statistics(self, fixture_id: int | str) -> list[dict[str, Any]]:
        return self.client.get_fixture_statistics(fixture_id)

    def get_fixture_lineups(self, fixture_id: int | str) -> list[dict[str, Any]]:
        return self.client.get_fixture_lineups(fixture_id)

    def get_injuries(
        self, team_id: Optional[int] = None, fixture_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        return self.client.get_injuries(team_id=team_id, fixture_id=fixture_id)

    @staticmethod
    def parse_events(api_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return APIClient.parse_events(api_events)

    @staticmethod
    def parse_statistics(api_stats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return APIClient.parse_statistics(api_stats)

    @staticmethod
    def parse_lineups(api_lineups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return APIClient.parse_lineups(api_lineups)
