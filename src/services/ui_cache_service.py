"""Build and refresh UI read-model cache tables (pipeline step J)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from src import db
from src import db_extended as ext
from src import db_pipeline as pipe_db
from src.api.helpers import team_meta
from src.cache.response_cache import invalidate_all, set_cache_meta
from src.team_flags import slugify

logger = logging.getLogger(__name__)

LIVE_STATUSES = ("1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED")


class UICacheService:
    def refresh_all(
        self,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        *,
        fast: bool = True,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> dict[str, Any]:
        from src.services.pipeline_cancel import PipelineCancelled

        def report(pct: float, msg: str) -> None:
            if progress_cb:
                progress_cb(pct, msg)

        report(1, "Preparing UI cache…")
        written = 0
        pipe_db.clear_match_cards_cache()
        pipe_db.clear_team_cards_cache()

        matches = db.get_upcoming_matches(limit=500, tournament_only=True)
        live = db.get_live_matches(tournament_only=True)
        recent = db.get_recent_matches(limit=100, tournament_only=True)
        seen: set[int] = set()
        all_matches = []
        for m in live + matches + recent:
            mid = int(m["id"])
            if mid not in seen:
                seen.add(mid)
                all_matches.append(m)

        ids = [int(m["id"]) for m in all_matches]
        pred_map = db.get_predictions_for_match_ids(ids) if ids else {}
        total = len(all_matches)

        for i, m in enumerate(all_matches):
            if should_cancel and should_cancel():
                raise PipelineCancelled()
            mid = int(m["id"])
            pred = dict(pred_map[mid]) if mid in pred_map else None
            home_meta = team_meta(m["home_team"])
            away_meta = team_meta(m["away_team"])
            card = self._match_to_card(m, pred, home_meta, away_meta)
            pipe_db.upsert_match_card_cache(card)
            written += 1
            if i % 5 == 0 or i == total - 1:
                pct = round((i + 1) / max(total, 1) * 70, 1)
                report(pct, f"Match cards {i + 1}/{total}")

        teams_written = self._refresh_team_cards(
            progress_cb=lambda p, msg: report(70 + p * 0.25, msg),
            fast=fast,
            should_cancel=should_cancel,
        )
        report(96, "Building home cache…")
        home_payload = self._build_home_payload(all_matches, pred_map)
        pipe_db.upsert_home_view_cache(home_payload)

        computed = datetime.utcnow().isoformat()
        set_cache_meta(data_version=computed, last_prediction_update=computed)
        invalidate_all()
        report(100, "UI cache ready")

        return {
            "match_cards": written,
            "team_cards": teams_written,
            "home_cache": True,
            "computed_at": computed,
        }

    def _match_to_card(
        self, m: Any, pred: Optional[dict], home_meta: dict, away_meta: dict
    ) -> dict[str, Any]:
        top_raw = pred.get("top_scorelines_json") if pred else None
        top_scorelines = json.loads(top_raw) if isinstance(top_raw, str) and top_raw else []
        best = top_scorelines[0] if top_scorelines else {}
        expl_raw = pred.get("explanation_json") if pred else None
        expl_summary = None
        if isinstance(expl_raw, str) and expl_raw:
            try:
                expl_summary = json.loads(expl_raw)
            except json.JSONDecodeError:
                pass
        elif isinstance(expl_raw, dict):
            expl_summary = expl_raw

        comp_raw = pred.get("completeness_flags_json") if pred else None
        completeness = json.loads(comp_raw) if isinstance(comp_raw, str) and comp_raw else comp_raw

        return {
            "match_id": int(m["id"]),
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "home_slug": home_meta["slug"],
            "away_slug": away_meta["slug"],
            "home_flag_url": home_meta["flag_url"],
            "away_flag_url": away_meta["flag_url"],
            "date": m["date"],
            "status": m.get("status"),
            "stage": m.get("stage"),
            "group_name": m.get("group_name"),
            "home_goals": m.get("home_goals"),
            "away_goals": m.get("away_goals"),
            "predicted_home": int(best.get("home", pred.get("predicted_home_goals", 0) if pred else 0)),
            "predicted_away": int(best.get("away", pred.get("predicted_away_goals", 0) if pred else 0)),
            "home_win_prob": pred.get("home_win_prob") if pred else None,
            "draw_prob": pred.get("draw_prob") if pred else None,
            "away_win_prob": pred.get("away_win_prob") if pred else None,
            "exact_score_prob": pred.get("exact_score_prob") if pred else None,
            "confidence_pct": pred.get("confidence_pct") if pred else None,
            "prediction_source_mode": pred.get("prediction_source_mode") if pred else None,
            "completeness_flags_json": completeness,
            "explanation_summary_json": expl_summary,
            "top_scorelines_json": top_scorelines[:3],
            "last_prediction_update": pred.get("generated_at") if pred else None,
        }

    def _refresh_team_cards(
        self,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        *,
        fast: bool = True,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> int:
        from src.services.pipeline_cancel import PipelineCancelled

        teams = ext.get_tournament_teams()
        written = 0
        total = len(teams)

        if fast:
            for i, t in enumerate(teams):
                if should_cancel and should_cancel():
                    raise PipelineCancelled()
                d = dict(t)
                name = d["name"]
                injuries = db.get_injuries_for_teams([name])
                meta = team_meta(name)
                players = ext.get_squad_players(int(d["id"])) if d.get("id") else []
                ratings = [dict(p).get("rating") for p in players if dict(p).get("rating")]
                avg_rating = sum(ratings) / len(ratings) if ratings else None
                pipe_db.upsert_team_card_cache({
                    "team_id": int(d["id"]),
                    "name": name,
                    "slug": d.get("slug") or meta["slug"],
                    "flag_url": meta["flag_url"],
                    "group_name": self._team_group(name),
                    "rating": avg_rating,
                    "recent_form": None,
                    "injury_count": len(injuries),
                    "momentum_score": None,
                })
                written += 1
                if progress_cb and (i % 4 == 0 or i == total - 1):
                    pct = round((i + 1) / max(total, 1) * 100, 1)
                    progress_cb(pct, f"Team cards {i + 1}/{total}")
            return written

        from src.analytics.momentum import MomentumEngine
        from src.analytics.team_form import TeamFormAnalyzer

        form_analyzer = TeamFormAnalyzer()
        momentum_engine = MomentumEngine()
        now = datetime.utcnow().isoformat()

        for i, t in enumerate(teams):
            if should_cancel and should_cancel():
                raise PipelineCancelled()
            d = dict(t)
            name = d["name"]
            injuries = db.get_injuries_for_teams([name])
            form = form_analyzer.compute(name, now)
            mom = momentum_engine.compute(name, now)
            group = self._team_group(name)
            meta = team_meta(name)
            players = ext.get_squad_players(int(d["id"])) if d.get("id") else []
            ratings = [p["rating"] for p in players if dict(p).get("rating")]
            avg_rating = sum(ratings) / len(ratings) if ratings else None

            pipe_db.upsert_team_card_cache({
                "team_id": int(d["id"]),
                "name": name,
                "slug": d.get("slug") or meta["slug"],
                "flag_url": meta["flag_url"],
                "group_name": group,
                "rating": avg_rating,
                "recent_form": form.form_last_5,
                "injury_count": len(injuries),
                "momentum_score": mom.score,
            })
            written += 1
            if progress_cb and (i % 5 == 0 or i == total - 1):
                progress_cb(
                    round((i + 1) / max(total, 1) * 100, 1),
                    f"Team cards {i + 1}/{total}",
                )
        return written

    @staticmethod
    def _team_group(team_name: str) -> Optional[str]:
        from src import db as db_mod
        with db_mod.get_connection() as conn:
            row = db_mod._execute(
                conn,
                "SELECT group_name FROM standings WHERE team = ? LIMIT 1",
                (team_name,),
            ).fetchone()
        return dict(row)["group_name"] if row else None

    def _build_home_payload(
        self, all_matches: list, pred_map: dict
    ) -> dict[str, Any]:
        live = [m for m in all_matches if m.get("status") in LIVE_STATUSES]
        upcoming = sorted(
            [m for m in all_matches if m.get("status") not in LIVE_STATUSES
             and m.get("status") not in ("FT", "AET", "PEN", "FINISHED")],
            key=lambda x: x.get("date", ""),
        )[:8]

        stats = db.get_platform_stats(tournament_only=True)
        computed = datetime.utcnow().isoformat()
        return {
            "stats": stats,
            "live": [
                self._match_to_card(
                    m,
                    dict(pred_map[int(m["id"])]) if int(m["id"]) in pred_map else None,
                    team_meta(m["home_team"]),
                    team_meta(m["away_team"]),
                )
                for m in live[:4]
            ],
            "upcoming": [
                self._match_to_card(
                    m,
                    dict(pred_map[int(m["id"])]) if int(m["id"]) in pred_map else None,
                    team_meta(m["home_team"]),
                    team_meta(m["away_team"]),
                )
                for m in upcoming
            ],
            "last_updated": computed,
            "data_version": computed,
        }
