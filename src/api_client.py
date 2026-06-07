"""HTTP client for API-Football v3 with football-data.org fallback."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

from src import config

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when an API request fails after retries."""

    def __init__(self, message: str, source: str = "unknown", status_code: Optional[int] = None):
        self.source = source
        self.status_code = status_code
        super().__init__(f"[{source}] {message}" + (f" (HTTP {status_code})" if status_code else ""))


class APIClient:
    """Unified client for football data APIs with retries and rate limiting."""

    def __init__(
        self,
        api_football_key: Optional[str] = None,
        football_data_key: Optional[str] = None,
    ):
        self.api_football_key = api_football_key or config.API_FOOTBALL_KEY
        self.football_data_key = football_data_key or config.FOOTBALL_DATA_KEY
        self._last_request_time: float = 0.0
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_ttl: float = 300.0  # 5 minutes
        self.last_warning: Optional[str] = None

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < config.MIN_REQUEST_INTERVAL:
            time.sleep(config.MIN_REQUEST_INTERVAL - elapsed)

    def _get_cached(self, key: str) -> Optional[Any]:
        if key in self._cache:
            ts, data = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        self._cache[key] = (time.time(), data)

    def _request(
        self,
        url: str,
        headers: dict[str, str],
        params: Optional[dict[str, Any]] = None,
        source: str = "api",
        use_cache: bool = True,
    ) -> dict[str, Any]:
        cache_key = f"{url}:{params}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        last_error: Optional[str] = None
        for attempt in range(config.MAX_RETRIES):
            try:
                self._rate_limit()
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=config.REQUEST_TIMEOUT,
                )
                self._last_request_time = time.time()

                if response.status_code == 429:
                    wait = config.RETRY_BACKOFF ** (attempt + 1) * 10
                    logger.warning("Rate limited by %s; waiting %.1fs", source, wait)
                    time.sleep(wait)
                    continue

                if response.status_code >= 500:
                    last_error = f"Server error: {response.status_code}"
                    time.sleep(config.RETRY_BACKOFF ** attempt)
                    continue

                if response.status_code >= 400:
                    raise APIError(
                        response.text[:200] or f"HTTP {response.status_code}",
                        source=source,
                        status_code=response.status_code,
                    )

                data = response.json()
                if use_cache:
                    self._set_cache(cache_key, data)
                return data

            except requests.Timeout:
                last_error = "Request timed out"
                logger.warning("%s timeout (attempt %d)", source, attempt + 1)
                time.sleep(config.RETRY_BACKOFF ** attempt)
            except requests.RequestException as exc:
                last_error = str(exc)
                logger.warning("%s request error: %s", source, exc)
                time.sleep(config.RETRY_BACKOFF ** attempt)

        raise APIError(last_error or "Unknown error", source=source)

    def _api_football_request(
        self, endpoint: str, params: Optional[dict[str, Any]] = None, use_cache: bool = True
    ) -> dict[str, Any]:
        if not self.api_football_key:
            raise APIError("API_FOOTBALL_KEY not configured", source="api-football")
        url = f"{config.API_FOOTBALL_BASE_URL}/{endpoint}"
        headers = {"x-apisports-key": self.api_football_key}
        return self._request(url, headers, params, source="api-football", use_cache=use_cache)

    def _football_data_request(
        self, endpoint: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        if not self.football_data_key:
            raise APIError("FOOTBALL_DATA_KEY not configured", source="football-data")
        url = f"{config.FOOTBALL_DATA_BASE_URL}/{endpoint}"
        headers = {"X-Auth-Token": self.football_data_key}
        return self._request(url, headers, params, source="football-data", use_cache=True)

    @staticmethod
    def _api_football_errors(data: dict[str, Any]) -> Optional[str]:
        """Return a human-readable message when API-Football embeds errors in a 200 response."""
        errors = data.get("errors") or {}
        if not errors:
            return None
        if isinstance(errors, dict):
            parts = [f"{k}: {v}" for k, v in errors.items() if v]
            return "; ".join(parts) if parts else str(errors)
        return str(errors)

    @staticmethod
    def _normalize_fixture(item: dict[str, Any], source: str = "api-football") -> dict[str, Any]:
        """Convert API response to a common fixture format."""
        if source == "api-football":
            fixture = item.get("fixture", item)
            league = item.get("league", {})
            teams = item.get("teams", {})
            goals = item.get("goals", {}) or {}
            return {
                "external_fixture_id": str(fixture.get("id", "")),
                "date": fixture.get("date", ""),
                "league": league.get("name", ""),
                "season": league.get("season"),
                "home_team": teams.get("home", {}).get("name", "Unknown"),
                "away_team": teams.get("away", {}).get("name", "Unknown"),
                "home_team_id": teams.get("home", {}).get("id"),
                "away_team_id": teams.get("away", {}).get("id"),
                "status": fixture.get("status", {}).get("short", "NS"),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
                "venue": (fixture.get("venue") or {}).get("name"),
                "raw": item,
            }

        # football-data.org format
        return {
            "external_fixture_id": str(item.get("id", "")),
            "date": item.get("utcDate", ""),
            "league": (item.get("competition") or {}).get("name", ""),
            "season": (item.get("season") or {}).get("startDate", "")[:4],
            "home_team": (item.get("homeTeam") or {}).get("name", "Unknown"),
            "away_team": (item.get("awayTeam") or {}).get("name", "Unknown"),
            "home_team_id": (item.get("homeTeam") or {}).get("id"),
            "away_team_id": (item.get("awayTeam") or {}).get("id"),
            "status": item.get("status", "SCHEDULED"),
            "home_goals": (item.get("score", {}).get("fullTime") or {}).get("home"),
            "away_goals": (item.get("score", {}).get("fullTime") or {}).get("away"),
            "venue": None,
            "raw": item,
        }

    def get_upcoming_matches(self, days_ahead: int = 14) -> list[dict[str, Any]]:
        """Fetch upcoming fixtures for the configured league/season."""
        self.last_warning = None
        try:
            today = datetime.utcnow().date()
            end = today + timedelta(days=days_ahead)
            data = self._api_football_request(
                "fixtures",
                {
                    "league": config.LEAGUE_ID,
                    "season": config.SEASON,
                    "from": today.isoformat(),
                    "to": end.isoformat(),
                    "timezone": "UTC",
                },
            )
            api_error = self._api_football_errors(data)
            fixtures = [self._normalize_fixture(f) for f in data.get("response", [])]
            if fixtures:
                return fixtures
            if api_error:
                self.last_warning = api_error
                logger.warning("API-Football upcoming: %s; trying fallback", api_error)
            return self._fallback_upcoming(days_ahead)
        except APIError as exc:
            self.last_warning = str(exc)
            logger.warning("API-Football upcoming failed: %s; trying fallback", exc)
            return self._fallback_upcoming(days_ahead)

    def get_recent_matches(self, days_back: int = 14) -> list[dict[str, Any]]:
        """Fetch recently finished fixtures."""
        try:
            today = datetime.utcnow().date()
            start = today - timedelta(days=days_back)
            data = self._api_football_request(
                "fixtures",
                {
                    "league": config.LEAGUE_ID,
                    "season": config.SEASON,
                    "from": start.isoformat(),
                    "to": today.isoformat(),
                    "timezone": "UTC",
                    "status": "FT",
                },
            )
            api_error = self._api_football_errors(data)
            fixtures = [self._normalize_fixture(f) for f in data.get("response", [])]
            if fixtures:
                return fixtures
            if api_error:
                self.last_warning = api_error
                logger.warning("API-Football recent: %s; trying fallback", api_error)
            return self._fallback_recent(days_back)
        except APIError as exc:
            self.last_warning = str(exc)
            logger.warning("API-Football recent failed: %s; trying fallback", exc)
            return self._fallback_recent(days_back)

    def get_live_matches(self) -> list[dict[str, Any]]:
        """Fetch currently live fixtures."""
        try:
            data = self._api_football_request(
                "fixtures",
                {"live": "all"},
                use_cache=False,
            )
            fixtures = [self._normalize_fixture(f) for f in data.get("response", [])]
            # Filter to configured league when league id is present in response
            league_fixtures = [
                f for f in fixtures
                if (f.get("raw") or {}).get("league", {}).get("id") == config.LEAGUE_ID
            ]
            return league_fixtures
        except APIError as exc:
            logger.warning("API-Football live failed: %s", exc)
            return []

    def get_fixture_statistics(self, fixture_id: int | str) -> list[dict[str, Any]]:
        """Fetch team statistics for a fixture."""
        try:
            data = self._api_football_request(
                "fixtures/statistics",
                {"fixture": fixture_id},
                use_cache=False,
            )
            return data.get("response", [])
        except APIError as exc:
            logger.warning("Statistics fetch failed for fixture %s: %s", fixture_id, exc)
            return []

    def get_fixture_lineups(self, fixture_id: int | str) -> list[dict[str, Any]]:
        """Fetch lineups for a fixture."""
        try:
            data = self._api_football_request(
                "fixtures/lineups",
                {"fixture": fixture_id},
                use_cache=False,
            )
            return data.get("response", [])
        except APIError as exc:
            logger.warning("Lineups fetch failed for fixture %s: %s", fixture_id, exc)
            return []

    def get_fixture_events(self, fixture_id: int | str) -> list[dict[str, Any]]:
        """Fetch match events (goals, cards, subs)."""
        try:
            data = self._api_football_request(
                "fixtures/events",
                {"fixture": fixture_id},
                use_cache=False,
            )
            return data.get("response", [])
        except APIError as exc:
            logger.warning("Events fetch failed for fixture %s: %s", fixture_id, exc)
            return []

    def get_fixture_players(self, fixture_id: int | str) -> list[dict[str, Any]]:
        """Fetch per-player match statistics and ratings for a fixture."""
        try:
            data = self._api_football_request(
                "fixtures/players",
                {"fixture": fixture_id},
                use_cache=False,
            )
            return data.get("response", [])
        except APIError as exc:
            logger.warning("Fixture players fetch failed for fixture %s: %s", fixture_id, exc)
            return []

    def get_standings(self, league: int, season: int) -> list[dict[str, Any]]:
        """Fetch league/tournament standings tables."""
        try:
            data = self._api_football_request(
                "standings",
                {"league": league, "season": season},
            )
            return data.get("response", [])
        except APIError as exc:
            logger.warning("Standings fetch failed for league %s season %s: %s", league, season, exc)
            return []

    def get_head_to_head(self, team1_id: int, team2_id: int) -> list[dict[str, Any]]:
        """Fetch historical fixtures between two teams."""
        try:
            data = self._api_football_request(
                "fixtures/headtohead",
                {"h2h": f"{team1_id}-{team2_id}"},
            )
            return data.get("response", [])
        except APIError as exc:
            logger.warning(
                "Head-to-head fetch failed for %s vs %s: %s", team1_id, team2_id, exc
            )
            return []

    def get_injuries(
        self, team_id: Optional[int] = None, fixture_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """Fetch injury reports by team or fixture."""
        params: dict[str, Any] = {}
        if fixture_id:
            params["fixture"] = fixture_id
        elif team_id:
            params["team"] = team_id
        else:
            params["league"] = config.LEAGUE_ID
            params["season"] = config.SEASON

        try:
            data = self._api_football_request("injuries", params)
            return data.get("response", [])
        except APIError as exc:
            logger.warning("Injuries fetch failed: %s", exc)
            return []

    def get_players(self, team_id: int, season: Optional[int] = None) -> list[dict[str, Any]]:
        """Fetch squad/player statistics for a team."""
        try:
            data = self._api_football_request(
                "players",
                {"team": team_id, "season": season or config.SEASON},
            )
            return data.get("response", [])
        except APIError as exc:
            logger.warning("Players fetch failed for team %s: %s", team_id, exc)
            return []

    def _fallback_upcoming(self, days_ahead: int) -> list[dict[str, Any]]:
        """Fallback to football-data.org for upcoming matches."""
        try:
            data = self._football_data_request(
                f"competitions/{config.FOOTBALL_DATA_COMPETITION_ID}/matches",
                {"status": "SCHEDULED"},
            )
            fixtures = [self._normalize_fixture(m, "football-data") for m in data.get("matches", [])]
            cutoff = datetime.utcnow() + timedelta(days=days_ahead)
            return [f for f in fixtures if f.get("date", "") <= cutoff.isoformat()]
        except APIError as exc:
            logger.error("Fallback upcoming also failed: %s", exc)
            return []

    def _fallback_recent(self, days_back: int) -> list[dict[str, Any]]:
        """Fallback to football-data.org for recent results."""
        try:
            data = self._football_data_request(
                f"competitions/{config.FOOTBALL_DATA_COMPETITION_ID}/matches",
                {"status": "FINISHED"},
            )
            fixtures = [self._normalize_fixture(m, "football-data") for m in data.get("matches", [])]
            cutoff = datetime.utcnow() - timedelta(days=days_back)
            return [f for f in fixtures if f.get("date", "") >= cutoff.isoformat()]
        except APIError as exc:
            logger.error("Fallback recent also failed: %s", exc)
            return []

    @staticmethod
    def parse_statistics(api_stats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Parse API-Football statistics into flat dicts keyed by team name."""
        result: dict[str, dict[str, Any]] = {}
        stat_map = {
            "Shots on Goal": "shots_on_target",
            "Total Shots": "shots",
            "Ball Possession": "possession",
            "Total passes": "passes",
            "Passes %": "pass_accuracy",
            "Corner Kicks": "corners",
            "Fouls": "fouls",
            "Yellow Cards": "yellow_cards",
            "Red Cards": "red_cards",
        }
        for team_block in api_stats:
            team_name = team_block.get("team", {}).get("name", "Unknown")
            parsed: dict[str, Any] = {}
            for stat in team_block.get("statistics", []):
                key = stat_map.get(stat.get("type", ""))
                if not key:
                    continue
                val = stat.get("value")
                if key == "possession" and isinstance(val, str):
                    val = float(val.replace("%", "").strip() or 0)
                elif key == "pass_accuracy" and isinstance(val, str):
                    val = float(val.replace("%", "").strip() or 0)
                parsed[key] = val
            result[team_name] = parsed
        return result

    @staticmethod
    def parse_lineups(api_lineups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse API-Football lineups into flat player records."""
        players: list[dict[str, Any]] = []
        for team_block in api_lineups:
            team_name = team_block.get("team", {}).get("name", "Unknown")
            for player in team_block.get("startXI", []):
                info = player.get("player", {})
                players.append(
                    {
                        "team": team_name,
                        "player_id": info.get("id"),
                        "player_name": info.get("name", "Unknown"),
                        "position": info.get("pos"),
                        "is_starting": True,
                        "rating": None,
                        "minutes": None,
                    }
                )
            for player in team_block.get("substitutes", []):
                info = player.get("player", {})
                players.append(
                    {
                        "team": team_name,
                        "player_id": info.get("id"),
                        "player_name": info.get("name", "Unknown"),
                        "position": info.get("pos"),
                        "is_starting": False,
                        "rating": None,
                        "minutes": None,
                    }
                )
        return players

    @staticmethod
    def parse_events(api_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse API-Football match events into flat records."""
        records: list[dict[str, Any]] = []
        for item in api_events:
            team = item.get("team", {})
            player = item.get("player", {})
            assist = item.get("assist") or {}
            time_info = item.get("time", {}) or {}
            records.append(
                {
                    "minute": time_info.get("elapsed"),
                    "extra_minute": time_info.get("extra"),
                    "team": team.get("name", "Unknown"),
                    "team_id": team.get("id"),
                    "player_id": player.get("id"),
                    "player_name": player.get("name"),
                    "assist_id": assist.get("id") if assist else None,
                    "assist_name": assist.get("name") if assist else None,
                    "event_type": item.get("type"),
                    "detail": item.get("detail"),
                    "comments": item.get("comments"),
                }
            )
        return records

    @staticmethod
    def parse_standings(api_standings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse API-Football standings response into flat group rows."""
        rows: list[dict[str, Any]] = []
        for block in api_standings:
            league = block.get("league", {})
            league_id = league.get("id")
            season = league.get("season")
            for group_table in league.get("standings") or []:
                group_name = None
                entries = group_table
                if isinstance(group_table, dict):
                    group_name = group_table.get("group")
                    entries = group_table.get("table") or []
                for entry in entries:
                    team = entry.get("team", {})
                    all_stats = entry.get("all") or {}
                    goals = all_stats.get("goals") or {}
                    rows.append(
                        {
                            "league_id": league_id,
                            "season": season,
                            "group_name": group_name or entry.get("group"),
                            "rank": entry.get("rank"),
                            "team_id": team.get("id"),
                            "team_name": team.get("name", "Unknown"),
                            "played": all_stats.get("played"),
                            "win": all_stats.get("win"),
                            "draw": all_stats.get("draw"),
                            "loss": all_stats.get("lose"),
                            "goals_for": goals.get("for"),
                            "goals_against": goals.get("against"),
                            "goal_diff": entry.get("goalsDiff"),
                            "points": entry.get("points"),
                            "form": entry.get("form"),
                            "status": entry.get("status"),
                            "description": entry.get("description"),
                        }
                    )
        return rows

    @staticmethod
    def parse_injuries(api_injuries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse API-Football injury records."""
        records: list[dict[str, Any]] = []
        for item in api_injuries:
            player = item.get("player", {})
            team = item.get("team", {})
            records.append(
                {
                    "player_id": player.get("id"),
                    "player_name": player.get("name", "Unknown"),
                    "team": team.get("name", "Unknown"),
                    "injury_type": player.get("type"),
                    "reason": player.get("reason"),
                    "expected_return": None,
                }
            )
        return records
