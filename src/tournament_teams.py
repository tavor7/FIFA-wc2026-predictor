"""WC 2026 tournament team roster (48 nations)."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from src.seed.load_seeds import _load_json
from src.team_flags import slugify
from src.team_names import normalize_team_name

if TYPE_CHECKING:
    from src.db import Row


@lru_cache
def get_wc2026_team_names() -> frozenset[str]:
    payload = _load_json("wc2026_groups.json")
    teams: set[str] = set()
    for members in (payload.get("groups") or {}).values():
        teams.update(members)
    return frozenset(teams)


@lru_cache
def get_wc2026_team_slugs() -> frozenset[str]:
    return frozenset(slugify(name) for name in get_wc2026_team_names())


def is_wc2026_team(name: str) -> bool:
    """True if name matches one of the 48 World Cup 2026 nations."""
    name = (name or "").strip()
    if not name:
        return False
    if name in get_wc2026_team_names():
        return True
    if slugify(name) in get_wc2026_team_slugs():
        return True
    canon = normalize_team_name(name)
    if canon in get_wc2026_team_names():
        return True
    return slugify(canon) in get_wc2026_team_slugs()


def filter_tournament_team_rows(teams: list[Row]) -> list[Row]:
    """Keep only rows for the 48 WC 2026 teams."""
    slugs = get_wc2026_team_slugs()
    names = get_wc2026_team_names()
    out: list[Row] = []
    for row in teams:
        n = row["name"]
        if n in names or slugify(n) in slugs:
            out.append(row)
    return out
