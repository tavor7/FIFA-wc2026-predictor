"""Streamlit dashboard — mobile-first FIFA World Cup prediction app."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import db  # noqa: E402
from src.predict import generate_predictions, retrain_and_predict  # noqa: E402
from src.sync_injuries import sync_injuries  # noqa: E402
from src.sync_live_data import sync_live_data  # noqa: E402
from src.sync_matches import sync_all_matches  # noqa: E402

st.set_page_config(
    page_title="WC 2026 Predictor",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)

db.init_db()

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
  }

  #MainMenu, footer, header { visibility: hidden; }

  .block-container {
    padding-top: 1rem !important;
    padding-bottom: 5rem !important;
    max-width: 720px !important;
  }

  .hero {
    background: linear-gradient(135deg, #0d2818 0%, #1b4332 45%, #2d6a4f 100%);
    border-radius: 20px;
    padding: 1.4rem 1.25rem;
    margin-bottom: 1rem;
    border: 1px solid rgba(0, 200, 83, 0.25);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
  }
  .hero h1 {
    color: #fff;
    font-size: 1.55rem;
    font-weight: 800;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.02em;
  }
  .hero p {
    color: rgba(255,255,255,0.78);
    font-size: 0.85rem;
    margin: 0;
    line-height: 1.45;
  }

  .stat-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.55rem;
    margin-bottom: 1rem;
  }
  .stat-card {
    background: #152820;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 0.75rem 0.5rem;
    text-align: center;
  }
  .stat-val {
    color: #00C853;
    font-size: 1.35rem;
    font-weight: 800;
    line-height: 1.1;
  }
  .stat-lbl {
    color: rgba(255,255,255,0.55);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-top: 0.2rem;
  }

  .match-card {
    background: #152820;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 1.1rem 1rem 1rem;
    margin-bottom: 0.85rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  }
  .match-card.live {
    border-color: rgba(255, 82, 82, 0.55);
    box-shadow: 0 0 0 1px rgba(255,82,82,0.15), 0 4px 24px rgba(255,82,82,0.12);
  }
  .match-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.85rem;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .badge {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.22rem 0.55rem;
    border-radius: 999px;
    background: rgba(0,200,83,0.15);
    color: #69f0ae;
  }
  .badge.live { background: rgba(255,82,82,0.2); color: #ff8a80; }
  .badge.finished { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.6); }
  .match-date { color: rgba(255,255,255,0.5); font-size: 0.75rem; }

  .teams-row {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  .team-name {
    font-weight: 700;
    font-size: 0.95rem;
    color: #f0f4f2;
    line-height: 1.25;
  }
  .team-name.home { text-align: right; }
  .team-name.away { text-align: left; }
  .score-box {
    background: rgba(0,0,0,0.35);
    border-radius: 12px;
    padding: 0.45rem 0.75rem;
    font-weight: 800;
    font-size: 1.15rem;
    color: #fff;
    min-width: 4.5rem;
    text-align: center;
  }
  .score-box.vs { font-size: 0.85rem; color: rgba(255,255,255,0.45); font-weight: 600; }

  .pick-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.65rem 0;
  }
  .pick-chip {
    background: rgba(0,200,83,0.12);
    border: 1px solid rgba(0,200,83,0.25);
    color: #b9f6ca;
    border-radius: 10px;
    padding: 0.35rem 0.6rem;
    font-size: 0.78rem;
    font-weight: 600;
  }
  .pick-chip.top {
    background: rgba(0,200,83,0.25);
    border-color: #00C853;
    color: #fff;
  }

  .prob-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.45rem;
    margin: 0.65rem 0;
  }
  .prob-item {
    background: rgba(0,0,0,0.25);
    border-radius: 10px;
    padding: 0.5rem 0.35rem;
    text-align: center;
  }
  .prob-pct { font-weight: 800; font-size: 0.95rem; color: #fff; }
  .prob-lbl { font-size: 0.62rem; color: rgba(255,255,255,0.5); text-transform: uppercase; margin-top: 0.1rem; }

  .explain-box {
    background: rgba(0,0,0,0.22);
    border-left: 3px solid #00C853;
    border-radius: 0 10px 10px 0;
    padding: 0.65rem 0.75rem;
    font-size: 0.82rem;
    color: rgba(255,255,255,0.82);
    line-height: 1.5;
    margin-top: 0.5rem;
  }

  .result-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #152820;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 0.75rem 0.85rem;
    margin-bottom: 0.45rem;
    gap: 0.5rem;
  }
  .result-teams { flex: 1; font-size: 0.85rem; font-weight: 600; color: #e8ede9; }
  .result-score {
    font-weight: 800;
    font-size: 1rem;
    color: #00C853;
    white-space: nowrap;
  }

  div[data-testid="stButton"] > button {
    border-radius: 12px !important;
    min-height: 2.75rem !important;
    font-weight: 600 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
  }
  div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #1b4332, #2d6a4f) !important;
    border-color: #00C853 !important;
  }

  .stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem;
    flex-wrap: wrap;
  }
  .stTabs [data-baseweb="tab"] {
    border-radius: 10px;
    padding: 0.4rem 0.65rem;
    font-size: 0.82rem;
    font-weight: 600;
  }

  @media (max-width: 480px) {
    .hero h1 { font-size: 1.3rem; }
    .team-name { font-size: 0.82rem; }
    .stat-val { font-size: 1.15rem; }
    .block-container { padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
  }
</style>
"""


def inject_styles() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _format_date(date_str: str, short: bool = False) -> str:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if short:
            return dt.strftime("%b %d · %H:%M")
        return dt.strftime("%a %b %d, %Y · %H:%M UTC")
    except (ValueError, TypeError):
        return date_str or "TBD"


def _status_badge(status: str) -> tuple[str, str]:
    live = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"}
    finished = {"FT", "AET", "PEN", "FINISHED"}
    if status in live:
        return "live", "● LIVE"
    if status in finished:
        return "finished", status
    return "", "UPCOMING"


def _row_to_dict(row) -> dict:
    return dict(row) if row else {}


def _attach_prediction(match_dict: dict) -> dict:
    pred = db.get_prediction(int(match_dict["id"]))
    if pred:
        top = json.loads(pred["top_scorelines_json"] or "[]")
        match_dict["prediction"] = {
            "predicted_home_goals": pred["predicted_home_goals"],
            "predicted_away_goals": pred["predicted_away_goals"],
            "home_win_prob": pred["home_win_prob"],
            "draw_prob": pred["draw_prob"],
            "away_win_prob": pred["away_win_prob"],
            "exact_score_prob": pred["exact_score_prob"],
            "top_scorelines": top,
            "explanation": pred["explanation"],
            "generated_at": pred["generated_at"],
        }
    return match_dict


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1>⚽ WC 2026 Predictor</h1>
          <p>Probability-based score predictions for your friend league.
          Research only — not betting advice.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stats() -> None:
    upcoming = len(db.get_upcoming_matches(limit=200))
    live = len(db.get_live_matches())
    preds = len(db.get_all_predictions())
    st.markdown(
        f"""
        <div class="stat-grid">
          <div class="stat-card"><div class="stat-val">{upcoming}</div><div class="stat-lbl">Upcoming</div></div>
          <div class="stat-card"><div class="stat-val">{live}</div><div class="stat-lbl">Live</div></div>
          <div class="stat-card"><div class="stat-val">{preds}</div><div class="stat-lbl">Predictions</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_match_card(match: dict, show_prediction: bool = True) -> None:
    home = match.get("home_team", "?")
    away = match.get("away_team", "?")
    status = match.get("status", "NS")
    hg, ag = match.get("home_goals"), match.get("away_goals")
    badge_cls, badge_txt = _status_badge(status)
    is_live = badge_cls == "live"

    if hg is not None and ag is not None:
        score_html = f"{hg} – {ag}"
    else:
        score_html = "vs"

    card_cls = "match-card live" if is_live else "match-card"
    badge_class = f"badge {badge_cls}".strip()

    st.markdown(
        f"""
        <div class="{card_cls}">
          <div class="match-meta">
            <span class="{badge_class}">{badge_txt}</span>
            <span class="match-date">{_format_date(match.get('date', ''), short=True)}</span>
          </div>
          <div class="teams-row">
            <div class="team-name home">{home}</div>
            <div class="score-box">{score_html}</div>
            <div class="team-name away">{away}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    venue = match.get("venue") or "Venue TBD"
    st.caption(f"📍 {venue}")

    if show_prediction and match.get("prediction"):
        pred = match["prediction"]
        top = pred.get("top_scorelines", [])[:5]

        chips = ""
        for i, sl in enumerate(top):
            cls = "pick-chip top" if i == 0 else "pick-chip"
            chips += f'<span class="{cls}">{sl["home"]}–{sl["away"]} · {sl["probability"]:.0%}</span>'
        st.markdown(f'<div class="pick-row">{chips}</div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="prob-row">
              <div class="prob-item">
                <div class="prob-pct">{pred.get("home_win_prob", 0):.0%}</div>
                <div class="prob-lbl">Home</div>
              </div>
              <div class="prob-item">
                <div class="prob-pct">{pred.get("draw_prob", 0):.0%}</div>
                <div class="prob-lbl">Draw</div>
              </div>
              <div class="prob-item">
                <div class="prob-pct">{pred.get("away_win_prob", 0):.0%}</div>
                <div class="prob-lbl">Away</div>
              </div>
            </div>
            <div class="explain-box">{pred.get("explanation", "")}</div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(f"Updated {_format_date(pred.get('generated_at', ''), short=True)}")


def render_sync_panel() -> None:
    with st.expander("🔄 Sync & update data", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Sync matches", use_container_width=True, type="primary"):
                with st.spinner("Fetching fixtures…"):
                    result = sync_all_matches()
                total = result.get("upcoming", {}).get("synced", 0) + result.get("recent", {}).get("synced", 0)
                if total:
                    st.success(f"Synced {total} matches")
                else:
                    st.warning("No new matches — check API keys / season")
                for key in ("upcoming", "recent"):
                    if result.get(key, {}).get("warning"):
                        st.error(result[key]["warning"])
                st.rerun()

            if st.button("Sync injuries", use_container_width=True):
                with st.spinner("Fetching injuries…"):
                    r = sync_injuries()
                st.success(f"{r.get('synced', 0)} injury records")
                st.rerun()

        with c2:
            if st.button("Generate picks", use_container_width=True, type="primary"):
                with st.spinner("Running model…"):
                    r = generate_predictions()
                st.success(f"{r.get('generated', 0)} predictions ready")
                st.rerun()

            if st.button("Sync live", use_container_width=True):
                with st.spinner("Updating live…"):
                    r = sync_live_data()
                st.success(f"Updated {r.get('updated', 0)} live matches")
                st.rerun()

        if st.button("Retrain model on finished matches", use_container_width=True):
            with st.spinner("Training…"):
                result = retrain_and_predict()
            train = result.get("training", {})
            if train.get("trained"):
                st.success(f"Trained on {train['samples']} matches")
            else:
                st.warning(train.get("message", "Not enough data yet"))
            st.rerun()


def _auto_bootstrap() -> None:
    """On cloud/first run, populate DB if empty."""
    if st.session_state.get("bootstrapped"):
        return
    st.session_state["bootstrapped"] = True
    if len(db.get_upcoming_matches(limit=1)) == 0:
        try:
            sync_all_matches()
            generate_predictions()
        except Exception:
            pass


def page_upcoming() -> None:
    matches = [_attach_prediction(_row_to_dict(m)) for m in db.get_upcoming_matches()]
    if not matches:
        st.info("No upcoming matches yet. Tap **Sync matches** above.")
        return
    for m in matches:
        render_match_card(m)


def page_live() -> None:
    matches = [_attach_prediction(_row_to_dict(m)) for m in db.get_live_matches()]
    if not matches:
        st.markdown(
            '<p style="color:rgba(255,255,255,0.5);text-align:center;padding:2rem 0;">'
            "No live matches right now.</p>",
            unsafe_allow_html=True,
        )
        return
    for m in matches:
        render_match_card(m)


def page_recent() -> None:
    matches = [_row_to_dict(m) for m in db.get_recent_matches(limit=30)]
    if not matches:
        st.info("No results yet. Sync matches first.")
        return
    for m in matches:
        hg = m.get("home_goals", "-")
        ag = m.get("away_goals", "-")
        st.markdown(
            f"""
            <div class="result-row">
              <div class="result-teams">{m['home_team']} vs {m['away_team']}</div>
              <div class="result-score">{hg} – {ag}</div>
            </div>
            <div style="color:rgba(255,255,255,0.4);font-size:0.72rem;margin:-0.25rem 0 0.5rem 0.85rem;">
              {_format_date(m['date'], short=True)}
            </div>
            """,
            unsafe_allow_html=True,
        )


def page_detail() -> None:
    upcoming = db.get_upcoming_matches(limit=100)
    recent = db.get_recent_matches(limit=50)
    all_matches = list(upcoming) + list(recent)
    if not all_matches:
        st.info("No matches available.")
        return

    options = {
        f"{m['home_team']} vs {m['away_team']}": int(m["id"])
        for m in all_matches
    }
    selected = st.selectbox("Choose match", list(options.keys()), label_visibility="collapsed")
    match = _attach_prediction(_row_to_dict(db.get_match_by_id(options[selected])))
    render_match_card(match)

    injuries = db.get_injuries_for_teams([match["home_team"], match["away_team"]])
    if injuries:
        st.markdown("**Injuries**")
        for i in injuries:
            st.markdown(
                f"- **{i['player_name']}** ({i['team']}) — {i.get('reason') or i.get('injury_type') or 'Unknown'}"
            )
    else:
        st.caption("No injury data available.")

    lineups = db.get_lineups(int(match["id"]))
    if lineups:
        st.markdown("**Lineups**")
        for team in {row["team"] for row in lineups}:
            starters = [r for r in lineups if r["team"] == team and r["is_starting"]]
            if starters:
                names = ", ".join(r["player_name"] for r in starters[:11])
                st.markdown(f"**{team}:** {names}")
    else:
        st.caption("Lineups not yet available.")


def main() -> None:
    inject_styles()
    _auto_bootstrap()
    render_hero()
    render_stats()
    render_sync_panel()

    tab1, tab2, tab3, tab4 = st.tabs(["📅 Upcoming", "🔴 Live", "✅ Results", "🔍 Detail"])

    with tab1:
        page_upcoming()
    with tab2:
        page_live()
    with tab3:
        page_recent()
    with tab4:
        page_detail()


if __name__ == "__main__":
    main()
