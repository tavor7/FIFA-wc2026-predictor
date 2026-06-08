"""Fetch and persist match events for finished and live matches."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import db
from src import db_extended as dbx
from src.api_client import APIClient

logger = logging.getLogger(__name__)

FINISHED_STATUSES = {"FT", "AET", "PEN", "FINISHED"}
LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"}
EVENT_STATUSES = FINISHED_STATUSES | LIVE_STATUSES


def sync_events_for_match(
    client: APIClient,
    match_id: int,
    external_fixture_id: str | int,
) -> int:
    """Fetch and persist events for a single match. Returns event count."""
    raw = client.get_fixture_events(external_fixture_id)
    if not raw:
        return 0

    parsed = client.parse_events(raw)
    dbx.clear_match_events(match_id)
    for event in parsed:
        dbx.upsert_match_event(
            match_id=match_id,
            minute=event.get("minute"),
            event_type=event.get("event_type") or "Unknown",
            team=event.get("team"),
            player_name=event.get("player_name"),
            player_id=event.get("player_id"),
            extra_minute=event.get("extra_minute"),
            detail=event.get("detail"),
        )
    return len(parsed)


def sync_events(
    client: Optional[APIClient] = None,
    include_recent: bool = True,
    *,
    tournament_only: bool = True,
    max_matches: Optional[int] = 25,
    live_only: bool = False,
) -> dict[str, Any]:
    """Sync match events for live and/or recent matches (scoped to avoid API timeouts)."""
    client = client or APIClient()
    db.init_db()

    statuses = list(LIVE_STATUSES)
    if include_recent and not live_only:
        statuses.extend(FINISHED_STATUSES)

    matches = db.get_matches_by_status(statuses, tournament_only=tournament_only)
    if live_only:
        live_set = set(LIVE_STATUSES)
        matches = [m for m in matches if m["status"] in live_set]
    if max_matches is not None and len(matches) > max_matches:
        matches = matches[-max_matches:]
    synced_matches = 0
    total_events = 0
    errors = 0

    for match in matches:
        ext_id = match["external_fixture_id"]
        try:
            count = sync_events_for_match(client, int(match["id"]), ext_id)
            if count > 0:
                synced_matches += 1
                total_events += count
        except Exception as exc:
            logger.error("Event sync failed for match %s: %s", ext_id, exc)
            errors += 1

    result = {
        "matches_checked": len(matches),
        "matches_with_events": synced_matches,
        "events_written": total_events,
        "errors": errors,
    }
    dbx.insert_sync_log(
        "sync_events",
        "ok" if errors == 0 else "partial",
        source="api-football",
        records_affected=total_events,
        finished_at=datetime.utcnow().isoformat(),
    )
    logger.info("Event sync: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_events())
