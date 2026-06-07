"""Simple knockout page payload for the current World Cup."""

from __future__ import annotations

from typing import Any

from src import db
from src.bracket.wc2026_knockout import (
    _is_knockout_match,
    _load_knockout_matches_from_db,
    _match_round_key,
)
from src.config import SEASON

ROUND_SECTIONS: list[tuple[str, str]] = [
    ("R32", "Round of 32"),
    ("R16", "Round of 16"),
    ("QF", "Quarter-finals"),
    ("SF", "Semi-finals"),
    ("F", "Final"),
    ("3P", "Third-place play-off"),
]

FINISHED_STATUSES = {"FT", "AET", "PEN", "FINISHED"}


def _season_matches(rows: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        m = dict(row)
        if m.get("season") in (None, SEASON):
            out.append(m)
    return out


def _group_by_round(matches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        rnd = _match_round_key(m)
        if rnd:
            grouped.setdefault(rnd, []).append(m)
    for rnd in grouped:
        grouped[rnd].sort(key=lambda x: x.get("date") or "")
    return grouped


def build_knockout_view() -> dict[str, Any]:
    """UI-friendly tournament view: real fixtures when available, group-stage next otherwise."""
    from src.api.helpers import match_with_prediction

    knockout_raw = _load_knockout_matches_from_db()
    upcoming = _season_matches(db.get_upcoming_matches(limit=80))
    finished = [
        dict(m)
        for m in db.get_all_finished_matches()
        if _is_knockout_match(dict(m)) and dict(m).get("season") in (None, SEASON)
    ]

    all_knockout = sorted(
        {m["id"]: m for m in [*knockout_raw, *finished] if m.get("id")}.values(),
        key=lambda x: x.get("date") or "",
    )
    by_round = _group_by_round(all_knockout)

    rounds: list[dict[str, Any]] = []
    for rnd_id, rnd_label in ROUND_SECTIONS:
        ms = by_round.get(rnd_id, [])
        if not ms:
            continue
        rounds.append(
            {
                "id": rnd_id,
                "label": rnd_label,
                "matches": [match_with_prediction(m) for m in ms],
            }
        )

    has_knockout = bool(rounds)
    live_knockout = any(
        (m.get("status") or "").upper() in {"1H", "2H", "HT", "ET", "LIVE", "IN_PLAY"}
        for m in all_knockout
    )

    if has_knockout:
        phase = "knockout_live" if live_knockout else "knockout"
        status = "Knockout stage is underway." if live_knockout else "Knockout stage fixtures."
    else:
        phase = "group_stage"
        first = upcoming[0]["date"][:10] if upcoming else None
        status = (
            f"Group stage · first match {first} · knockout rounds appear here once the group stage ends."
            if first
            else "Knockout rounds will appear here once elimination fixtures are scheduled."
        )

    next_matches = (
        [match_with_prediction(m) for m in upcoming[:24]]
        if not has_knockout
        else [
            match_with_prediction(m)
            for m in all_knockout
            if (m.get("status") or "").upper() not in FINISHED_STATUSES
        ][:24]
    )

    return {
        "title": "World Cup 2026",
        "season": SEASON,
        "phase": phase,
        "status": status,
        "has_knockout": has_knockout,
        "rounds": rounds,
        "next_matches": next_matches,
        "counts": {
            "upcoming": len(upcoming),
            "knockout_fixtures": len(all_knockout),
        },
    }
