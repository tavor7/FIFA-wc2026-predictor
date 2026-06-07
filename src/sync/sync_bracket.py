"""Derive knockout bracket nodes from match stage/round metadata."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import config, db
from src import db_extended as dbx
from src.api_client import APIClient

logger = logging.getLogger(__name__)

KNOCKOUT_KEYWORDS = (
    "round of 16", "round of 32", "quarter", "semi", "final", "3rd place", "third place",
)
GROUP_KEYWORDS = ("group",)


def _normalize_stage(league_info: dict[str, Any]) -> str:
    """Map API league round/stage fields to a bracket stage label."""
    round_name = (league_info.get("round") or "").strip()
    lower = round_name.lower()
    if any(k in lower for k in GROUP_KEYWORDS):
        return "Group Stage"
    if "final" in lower and "semi" not in lower and "quarter" not in lower:
        if "3rd" in lower or "third" in lower:
            return "Third Place"
        return "Final"
    if "semi" in lower:
        return "Semi-Finals"
    if "quarter" in lower:
        return "Quarter-Finals"
    if "32" in lower:
        return "Round of 32"
    if "16" in lower:
        return "Round of 16"
    return round_name or "Unknown"


def _round_sort_key(round_name: str) -> tuple[int, str]:
    lower = round_name.lower()
    order = [
        ("round of 32", 1),
        ("round of 16", 2),
        ("quarter", 3),
        ("semi", 4),
        ("3rd", 5),
        ("third", 5),
        ("final", 6),
    ]
    for token, rank in order:
        if token in lower:
            return (rank, round_name)
    return (99, round_name)


def _is_knockout_round(round_name: str) -> bool:
    lower = round_name.lower()
    return any(k in lower for k in KNOCKOUT_KEYWORDS)


def _extract_fixture_meta(fixture: dict[str, Any]) -> dict[str, Any]:
    """Pull stage/round/group from a normalized fixture's raw API payload."""
    raw = fixture.get("raw") or {}
    league = raw.get("league") or {}
    return {
        "stage": _normalize_stage(league),
        "round_name": league.get("round") or "",
        "group_name": league.get("group") or "",
    }


def sync_bracket(
    client: Optional[APIClient] = None,
    days_back: int = 60,
    days_ahead: int = 60,
) -> dict[str, Any]:
    """
    Build bracket_nodes from fixture round/stage metadata.
    Uses upcoming + recent API fixtures to capture knockout slots.
    """
    client = client or APIClient()
    db.init_db()
    dbx.clear_bracket_nodes()

    fixtures = client.get_recent_matches(days_back=days_back)
    fixtures.extend(client.get_upcoming_matches(days_ahead=days_ahead))

    seen_ext: set[str] = set()
    knockout_fixtures: list[dict[str, Any]] = []
    for fixture in fixtures:
        ext_id = str(fixture.get("external_fixture_id", ""))
        if not ext_id or ext_id in seen_ext:
            continue
        seen_ext.add(ext_id)
        meta = _extract_fixture_meta(fixture)
        if _is_knockout_round(meta["round_name"]):
            knockout_fixtures.append({**fixture, **meta})

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fx in knockout_fixtures:
        key = (fx["stage"], fx["round_name"])
        buckets.setdefault(key, []).append(fx)

    written = 0
    errors = 0
    for (stage, round_name), items in sorted(
        buckets.items(), key=lambda kv: (_round_sort_key(kv[0][1]), kv[0][0])
    ):
        items.sort(key=lambda f: f.get("date", ""))
        for slot, fx in enumerate(items, start=1):
            try:
                match_id = db.upsert_match(
                    external_fixture_id=str(fx["external_fixture_id"]),
                    date=fx.get("date", ""),
                    league=fx.get("league", ""),
                    season=int(fx.get("season") or config.SEASON),
                    home_team=fx.get("home_team", "Unknown"),
                    away_team=fx.get("away_team", "Unknown"),
                    status=fx.get("status", "NS"),
                    home_goals=fx.get("home_goals"),
                    away_goals=fx.get("away_goals"),
                    venue=fx.get("venue"),
                    home_team_id=fx.get("home_team_id"),
                    away_team_id=fx.get("away_team_id"),
                )
                dbx.update_match_metadata(
                    match_id,
                    stage=fx.get("stage"),
                    group_name=fx.get("group_name") or None,
                    round_name=fx.get("round_name") or None,
                )

                winner_id = None
                status = fx.get("status", "")
                if status in ("FT", "AET", "PEN", "FINISHED"):
                    hg, ag = fx.get("home_goals"), fx.get("away_goals")
                    if hg is not None and ag is not None:
                        if hg > ag:
                            winner_id = fx.get("home_team_id")
                        elif ag > hg:
                            winner_id = fx.get("away_team_id")

                dbx.upsert_bracket_node(
                    stage=stage,
                    round_name=round_name,
                    slot=slot,
                    match_id=match_id,
                    home_team=fx.get("home_team"),
                    away_team=fx.get("away_team"),
                    winner_team_id=winner_id,
                )
                written += 1
            except Exception as exc:
                logger.error(
                    "Bracket sync failed for %s / %s slot %d: %s",
                    stage, round_name, slot, exc,
                )
                errors += 1

    result = {
        "knockout_fixtures": len(knockout_fixtures),
        "nodes_written": written,
        "errors": errors,
    }
    dbx.insert_sync_log(
        "sync_bracket",
        "ok" if errors == 0 else "partial",
        source="api-football",
        records_affected=written,
        finished_at=datetime.utcnow().isoformat(),
    )
    logger.info("Bracket sync: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_bracket())
