"""Orchestrate data sync jobs and freshness tracking."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import db
from src import db_extended as ext
from src.api_client import APIClient
from src.sync.sync_bracket import sync_bracket
from src.sync.sync_events import sync_events
from src.sync.sync_squads import sync_squads
from src.sync.sync_standings import sync_standings
from src.sync_historical import sync_historical_seasons
from src.sync_injuries import sync_injuries
from src.sync_live_data import sync_live_data
from src.sync_matches import sync_all_matches

logger = logging.getLogger(__name__)


def _log_sync(job: str, result: dict[str, Any], source: str = "api-football") -> None:
    records = (
        result.get("updated")
        or result.get("rows_written")
        or result.get("total_synced")
        or result.get("matches")
        or 0
    )
    errors = result.get("errors", 0)
    ext.insert_sync_log(
        job,
        "ok" if errors == 0 else "partial",
        source=source,
        records_affected=records,
        finished_at=datetime.utcnow().isoformat(),
    )


class DataSyncService:
    def __init__(self, client: Optional[APIClient] = None, *, fast: bool = True):
        self.client = client
        self.fast = fast

    def sync_fixtures(self) -> dict[str, Any]:
        if self.fast:
            # Bundled seeds cover the schedule; light API refresh only
            result = sync_all_matches(days_ahead=21, days_back=7)
            sync_standings()
        else:
            result = sync_all_matches(days_ahead=60, days_back=14)
            sync_standings()
            sync_bracket()
        ext.upsert_data_freshness("fixtures", 100.0, source="api-football")
        _log_sync("sync_fixtures", result)
        return result

    def sync_injuries(self) -> dict[str, Any]:
        result = sync_injuries()
        ext.upsert_data_freshness("injuries", 100.0, source="api-football")
        _log_sync("sync_injuries", result)
        return result

    def ensure_fc26_squads(self, min_players: int = 400) -> dict[str, Any]:
        """Load EA FC 26 squad ratings from bundled CSV when missing."""
        fc26_total = ext.count_fc26_players()
        if fc26_total >= min_players:
            return {"status": "skipped", "players": fc26_total}
        from src.seed.import_fc26_players import FC26_CSV_PATH, import_fc26_players

        logger.info("Importing FC26 squads (%s players in DB)", fc26_total)
        result = import_fc26_players(download=not FC26_CSV_PATH.is_file())
        result["status"] = "imported"
        _log_sync("import_fc26_players", result, source="kaggle_fc26")
        return result

    def sync_team_stats(self) -> dict[str, Any]:
        fc26 = self.ensure_fc26_squads()
        # Kaggle has <26 players for some nations — API fills the rest
        result = sync_squads(fill_thin_squads=True, thin_teams_only=self.fast)
        ext.upsert_data_freshness("team_stats", 100.0, source="api-football")
        ext.upsert_data_freshness("player_stats", 90.0, source="api-football")
        _log_sync("sync_team_stats", result)
        return {"fc26": fc26, **result}

    def sync_live(self) -> dict[str, Any]:
        live = db.get_live_matches()
        result = sync_live_data()
        if live or result.get("live_from_api", 0) > 0:
            sync_events(tournament_only=True, max_matches=20, live_only=True)
            ext.upsert_data_freshness("lineups", 95.0, source="live")
            ext.upsert_data_freshness("player_stats", 95.0, source="live")
        ext.upsert_data_freshness("fixtures", 100.0, source="live")
        _log_sync("sync_live", result, source="live")
        return result

    def sync_historical_data(self) -> dict[str, Any]:
        from src.seed.historical_loader import load_historical_seeds

        seed_result = load_historical_seeds()
        api_result = sync_historical_seasons()
        ext.upsert_data_freshness("fixtures", 100.0, source="historical")
        _log_sync("sync_historical", {"total_synced": seed_result.get("matches", 0) + api_result.get("total_synced", 0)}, source="historical")
        return {"seeds": seed_result, "api": api_result}

    def full_sync(self) -> dict[str, Any]:
        if len(db.get_all_finished_matches()) < 10:
            self.sync_historical_data()
        fixtures = self.sync_fixtures()
        injuries = self.sync_injuries()
        stats = self.sync_team_stats()
        return {"fixtures": fixtures, "injuries": injuries, "team_stats": stats}
