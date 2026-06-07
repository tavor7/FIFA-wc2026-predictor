"""Sync live match data: scores, stats, lineups, and events."""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.api_client import APIClient
from src.sync.sync_events import sync_events_for_match

logger = logging.getLogger(__name__)

LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"}


def _sync_fixture_details(client: APIClient, match_id: int, external_id: str) -> int:
    """Update statistics, lineups, and events for a single fixture."""
    events_written = 0

    stats_raw = client.get_fixture_statistics(external_id)
    if stats_raw:
        parsed = client.parse_statistics(stats_raw)
        for team, stats in parsed.items():
            db.upsert_team_stats(match_id, team, stats)

    lineups_raw = client.get_fixture_lineups(external_id)
    if lineups_raw:
        db.clear_lineups_for_match(match_id)
        for player in client.parse_lineups(lineups_raw):
            db.upsert_lineup(
                match_id=match_id,
                team=player["team"],
                player_id=player.get("player_id"),
                player_name=player["player_name"],
                position=player.get("position"),
                is_starting=player.get("is_starting", True),
                rating=player.get("rating"),
                minutes=player.get("minutes"),
            )

    try:
        events_written = sync_events_for_match(client, match_id, external_id)
    except Exception as exc:
        logger.warning("Event sync failed for live match %s: %s", external_id, exc)

    return events_written


def sync_live_data(client: APIClient | None = None) -> dict[str, Any]:
    """
    Poll live matches and update scores, status, stats, lineups, and events.
    Also refreshes any locally tracked live matches.
    """
    client = client or APIClient()
    db.init_db()

    live_fixtures = client.get_live_matches()
    local_live = db.get_live_matches()
    updated = 0
    events_written = 0
    errors = 0

    # Build lookup of external ids from API
    api_by_id = {f["external_fixture_id"]: f for f in live_fixtures}

    # Update API live fixtures
    for fixture in live_fixtures:
        try:
            match_id = db.upsert_match(
                external_fixture_id=str(fixture["external_fixture_id"]),
                date=fixture.get("date", ""),
                league=fixture.get("league", ""),
                season=int(fixture.get("season") or 0),
                home_team=fixture.get("home_team", "Unknown"),
                away_team=fixture.get("away_team", "Unknown"),
                status=fixture.get("status", "LIVE"),
                home_goals=fixture.get("home_goals"),
                away_goals=fixture.get("away_goals"),
                venue=fixture.get("venue"),
                home_team_id=fixture.get("home_team_id"),
                away_team_id=fixture.get("away_team_id"),
            )
            events_written += _sync_fixture_details(
                client, match_id, str(fixture["external_fixture_id"])
            )
            updated += 1
        except Exception as exc:
            logger.error("Live sync failed for %s: %s", fixture.get("external_fixture_id"), exc)
            errors += 1

    # Refresh locally tracked live matches not returned by API (edge case)
    for row in local_live:
        ext_id = str(row["external_fixture_id"])
        if ext_id not in api_by_id:
            try:
                events_written += _sync_fixture_details(client, int(row["id"]), ext_id)
            except Exception as exc:
                logger.warning("Could not refresh local live match %s: %s", ext_id, exc)

    return {
        "live_from_api": len(live_fixtures),
        "updated": updated,
        "events_written": events_written,
        "errors": errors,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_live_data())
