"""Official FIFA WC 2026 knockout bracket template (48-team format, Appendix A)."""

from __future__ import annotations

from typing import Any, Optional

from src import db
from src.team_profiles import normalize_team_name

# Match codes M73–M104 per FIFA regulations (knockout stage).
MATCHES: dict[str, dict[str, Any]] = {
    "M73": {"round": "R32", "label": "2A v 2B", "pathway": 1, "quadrant": "blue", "row": 0},
    "M74": {"round": "R32", "label": "1E v 3ABCDF", "pathway": 1, "quadrant": "blue", "row": 1},
    "M75": {"round": "R32", "label": "1F v 2C", "pathway": 1, "quadrant": "blue", "row": 2},
    "M76": {"round": "R32", "label": "1C v 2F", "pathway": 2, "quadrant": "green", "row": 0},
    "M77": {"round": "R32", "label": "1I v 3CDFGH", "pathway": 1, "quadrant": "blue", "row": 3},
    "M78": {"round": "R32", "label": "2E v 2I", "pathway": 2, "quadrant": "green", "row": 1},
    "M79": {"round": "R32", "label": "1A v 3CEFHI", "pathway": 2, "quadrant": "green", "row": 2},
    "M80": {"round": "R32", "label": "1L v 3EHIJK", "pathway": 2, "quadrant": "green", "row": 3},
    "M81": {"round": "R32", "label": "1D v 3BEFIJ", "pathway": 1, "quadrant": "teal", "row": 0},
    "M82": {"round": "R32", "label": "1G v 3AEHIJ", "pathway": 1, "quadrant": "teal", "row": 1},
    "M83": {"round": "R32", "label": "2K v 2L", "pathway": 1, "quadrant": "teal", "row": 2},
    "M84": {"round": "R32", "label": "1H v 2J", "pathway": 1, "quadrant": "teal", "row": 3},
    "M85": {"round": "R32", "label": "1B v 3EFGIJ", "pathway": 2, "quadrant": "red", "row": 0},
    "M86": {"round": "R32", "label": "1J v 2H", "pathway": 2, "quadrant": "red", "row": 1},
    "M87": {"round": "R32", "label": "1K v 3DEIJL", "pathway": 2, "quadrant": "red", "row": 2},
    "M88": {"round": "R32", "label": "2D v 2G", "pathway": 2, "quadrant": "red", "row": 3},
    "M89": {"round": "R16", "label": "W74 v W77", "pathway": 1, "quadrant": "blue", "row": 0},
    "M90": {"round": "R16", "label": "W73 v W75", "pathway": 1, "quadrant": "blue", "row": 1},
    "M91": {"round": "R16", "label": "W76 v W78", "pathway": 2, "quadrant": "green", "row": 0},
    "M92": {"round": "R16", "label": "W79 v W80", "pathway": 2, "quadrant": "green", "row": 1},
    "M93": {"round": "R16", "label": "W83 v W84", "pathway": 1, "quadrant": "teal", "row": 0},
    "M94": {"round": "R16", "label": "W81 v W82", "pathway": 1, "quadrant": "teal", "row": 1},
    "M95": {"round": "R16", "label": "W86 v W88", "pathway": 2, "quadrant": "red", "row": 0},
    "M96": {"round": "R16", "label": "W85 v W87", "pathway": 2, "quadrant": "red", "row": 1},
    "M97": {"round": "QF", "label": "W89 v W90", "pathway": 1, "quadrant": "blue", "row": 0},
    "M98": {"round": "QF", "label": "W93 v W94", "pathway": 1, "quadrant": "teal", "row": 0},
    "M99": {"round": "QF", "label": "W91 v W92", "pathway": 2, "quadrant": "green", "row": 0},
    "M100": {"round": "QF", "label": "W95 v W96", "pathway": 2, "quadrant": "red", "row": 0},
    "M101": {"round": "SF", "label": "W97 v W98", "pathway": 1, "quadrant": "magenta", "row": 0},
    "M102": {"round": "SF", "label": "W99 v W100", "pathway": 2, "quadrant": "magenta", "row": 0},
    "M103": {"round": "3P", "label": "L101 v L102", "pathway": 0, "quadrant": "bronze", "row": 0},
    "M104": {"round": "F", "label": "W101 v W102", "pathway": 0, "quadrant": "final", "row": 0},
}

ROUND_ORDER = ["R32", "R16", "QF", "SF", "F"]

KNOCKOUT_ROUND_CODES: dict[str, list[str]] = {
    "R32": [f"M{n}" for n in range(73, 89)],
    "R16": [f"M{n}" for n in range(89, 97)],
    "QF": [f"M{n}" for n in range(97, 101)],
    "SF": ["M101", "M102"],
    "3P": ["M103"],
    "F": ["M104"],
}

_KNOCKOUT_KEYWORDS = (
    "round of 32", "round of 16", "quarter", "semi", "final", "3rd", "third", "knockout",
)


def _is_knockout_match(row: dict[str, Any]) -> bool:
    stage = (row.get("stage") or "").lower()
    rnd = (row.get("round_name") or "").lower()
    if "group" in stage or "group" in rnd:
        return False
    text = f"{stage} {rnd}"
    return any(k in text for k in _KNOCKOUT_KEYWORDS)


def _match_round_key(row: dict[str, Any]) -> Optional[str]:
    stage = (row.get("stage") or "").lower()
    rnd = (row.get("round_name") or "").lower()
    text = f"{stage} {rnd}"
    if "3rd" in text or "third" in text:
        return "3P"
    if "semi" in text:
        return "SF"
    if "quarter" in text:
        return "QF"
    if "32" in text:
        return "R32"
    if "16" in text:
        return "R16"
    if "final" in text and "semi" not in text and "quarter" not in text:
        return "F"
    return None


def _match_overlay(match_row: Any) -> dict[str, Any]:
    m = dict(match_row)
    hg, ag = m.get("home_goals"), m.get("away_goals")
    score = None
    winner = None
    if hg is not None and ag is not None:
        score = f"{hg}–{ag}"
        if hg > ag:
            winner = m.get("home_team")
        elif ag > hg:
            winner = m.get("away_team")
    return {
        "match_id": m.get("id"),
        "home_team": m.get("home_team"),
        "away_team": m.get("away_team"),
        "score": score,
        "winner": winner,
        "status": m.get("status"),
        "date": m.get("date"),
    }


def _load_knockout_matches_from_db() -> list[dict[str, Any]]:
    """Knockout fixtures only (excludes group-stage matches)."""
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for row in db.get_all_finished_matches():
        r = dict(row)
        if _is_knockout_match(r) and r.get("id") not in seen:
            out.append(r)
            seen.add(r.get("id"))
    for row in db.get_upcoming_matches(limit=200):
        r = dict(row)
        if _is_knockout_match(r) and r.get("id") not in seen:
            out.append(r)
            seen.add(r.get("id"))
    return out


def _apply_db_overlays(payload: dict[str, dict[str, Any]]) -> None:
    """Fill team names and scores when knockout matches exist in DB."""
    by_round: dict[str, list[dict[str, Any]]] = {}
    for m in _load_knockout_matches_from_db():
        rnd = _match_round_key(m)
        if rnd:
            by_round.setdefault(rnd, []).append(m)

    for rnd, codes in KNOCKOUT_ROUND_CODES.items():
        matches = sorted(by_round.get(rnd, []), key=lambda x: x.get("date") or "")
        for i, code in enumerate(codes):
            if i < len(matches):
                payload[code].update(_match_overlay(matches[i]))


def build_knockout_bracket(apply_db: bool = True) -> dict[str, Any]:
    """Full bracket tree for the knockout UI."""
    matches = {
        code: {"code": code, **meta, "display": meta["label"]}
        for code, meta in MATCHES.items()
    }

    if apply_db:
        _apply_db_overlays(matches)
        for m in matches.values():
            if m.get("home_team") and m.get("away_team"):
                m["display"] = f"{normalize_team_name(m['home_team'])} v {normalize_team_name(m['away_team'])}"
                if m.get("score"):
                    m["display"] += f" ({m['score']})"

    def pick(codes: list[str]) -> list[dict[str, Any]]:
        return [matches[c] for c in codes]

    return {
        "title": "FIFA World Cup 2026 — Knockout Stage",
        "subtitle": "48 teams → Round of 32 → Final · Pathway 1 (left) meets Pathway 2 (right) at the semi-finals",
        "rounds": ROUND_ORDER,
        "pathway_1": {
            "label": "PATHWAY 1",
            "blue": {
                "R32": pick(["M73", "M74", "M75", "M77"]),
                "R16": pick(["M89", "M90"]),
                "QF": pick(["M97"]),
            },
            "teal": {
                "R32": pick(["M81", "M82", "M83", "M84"]),
                "R16": pick(["M93", "M94"]),
                "QF": pick(["M98"]),
            },
            "SF": pick(["M101"]),
        },
        "pathway_2": {
            "label": "PATHWAY 2",
            "green": {
                "R32": pick(["M76", "M78", "M79", "M80"]),
                "R16": pick(["M91", "M92"]),
                "QF": pick(["M99"]),
            },
            "red": {
                "R32": pick(["M85", "M86", "M87", "M88"]),
                "R16": pick(["M95", "M96"]),
                "QF": pick(["M100"]),
            },
            "SF": pick(["M102"]),
        },
        "center": {
            "final": matches["M104"],
            "bronze": matches["M103"],
        },
        "legend": {
            "1X": "Winner of group X",
            "2X": "Runner-up of group X",
            "3ABCDF": "Best 3rd-place team from listed groups",
            "WX": "Winner of match X",
        },
    }
