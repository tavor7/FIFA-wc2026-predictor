"""Streamlit dashboard — clean, mobile-first WC 2026 predictor."""

from __future__ import annotations

import html
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
    page_title="WC 2026 · Research Tool",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)

db.init_db()

AUTHOR = "Amit Tavor"
DISCLAIMER_SHORT = "For educational & research purposes only. Not betting or financial advice."
DISCLAIMER_FULL = (
    "This tool is for educational and research purposes only. "
    "All outputs are probabilistic estimates, not guaranteed predictions. "
    "Not affiliated with FIFA. No betting, gambling, or wagering advice. "
    "Use at your own discretion."
)

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }

  #MainMenu, footer, header { visibility: hidden; height: 0; }

  .block-container {
    padding: 0.75rem 1rem 4rem !important;
    max-width: 480px !important;
  }

  /* ── Header ── */
  .app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0 1.25rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 1.25rem;
  }
  .app-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: #fafafa;
    letter-spacing: -0.03em;
    margin: 0;
  }
  .app-sub {
    font-size: 0.7rem;
    color: #71717a;
    margin: 0.15rem 0 0;
    font-weight: 400;
  }
  .app-credit {
    font-size: 0.6875rem;
    color: #52525b;
    margin-top: 0.2rem;
  }

  .disclaimer-banner {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 0.625rem 0.875rem;
    margin-bottom: 1rem;
    font-size: 0.6875rem;
    color: #71717a;
    line-height: 1.45;
  }
  .disclaimer-banner strong { color: #a1a1aa; font-weight: 600; }

  .site-footer {
    margin-top: 2rem;
    padding-top: 1.25rem;
    border-top: 1px solid rgba(255,255,255,0.06);
    text-align: center;
  }
  .footer-credit {
    font-size: 0.8125rem;
    font-weight: 600;
    color: #a1a1aa;
    margin: 0 0 0.35rem;
  }
  .footer-disclaimer {
    font-size: 0.6875rem;
    color: #52525b;
    line-height: 1.5;
    max-width: 360px;
    margin: 0 auto;
  }

  .pick-disclaimer {
    font-size: 0.625rem;
    color: #52525b;
    margin-top: 0.625rem;
    line-height: 1.4;
  }

  /* ── Match card ── */
  .card {
    background: #18181B;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 1.25rem 1.125rem 1rem;
    margin-bottom: 0.75rem;
  }
  .card.live { border-color: rgba(239,68,68,0.35); }

  .card-time {
    font-size: 0.6875rem;
    font-weight: 500;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 1rem;
  }
  .card-time .dot-live {
    color: #ef4444;
    margin-right: 0.35rem;
  }

  .matchup {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1.125rem;
  }
  .team {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #fafafa;
    line-height: 1.3;
    letter-spacing: -0.02em;
  }
  .team.left  { text-align: right; }
  .team.right { text-align: left; }

  .pick-badge {
    text-align: center;
  }
  .pick-score {
    font-size: 1.625rem;
    font-weight: 700;
    color: #fafafa;
    letter-spacing: -0.04em;
    line-height: 1;
  }
  .pick-label {
    font-size: 0.625rem;
    font-weight: 600;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.3rem;
  }
  .pick-conf {
    font-size: 0.75rem;
    font-weight: 500;
    color: #a1a1aa;
    margin-top: 0.2rem;
  }

  /* outcome bar */
  .bar-wrap { margin-bottom: 0.25rem; }
  .bar {
    display: flex;
    height: 4px;
    border-radius: 99px;
    overflow: hidden;
    background: rgba(255,255,255,0.06);
  }
  .bar-h { background: #fafafa; }
  .bar-d { background: #52525b; }
  .bar-a { background: #3f3f46; }

  .bar-labels {
    display: flex;
    justify-content: space-between;
    margin-top: 0.4rem;
  }
  .bar-lbl {
    font-size: 0.6875rem;
    color: #71717a;
    font-weight: 500;
  }
  .bar-lbl strong { color: #d4d4d8; font-weight: 600; }

  /* result row */
  .result {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.875rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    gap: 0.75rem;
  }
  .result:last-child { border-bottom: none; }
  .result-info { flex: 1; min-width: 0; }
  .result-teams {
    font-size: 0.875rem;
    font-weight: 500;
    color: #fafafa;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .result-date { font-size: 0.6875rem; color: #71717a; margin-top: 0.15rem; }
  .result-score {
    font-size: 0.9375rem;
    font-weight: 700;
    color: #fafafa;
    flex-shrink: 0;
  }

  .empty {
    text-align: center;
    padding: 3rem 1rem;
    color: #71717a;
    font-size: 0.875rem;
  }

  /* streamlit overrides */
  div[data-testid="stButton"] > button {
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.8125rem !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    background: #18181B !important;
    color: #fafafa !important;
    min-height: 2.5rem !important;
    transition: background 0.15s !important;
  }
  div[data-testid="stButton"] > button:hover {
    background: #27272a !important;
    border-color: rgba(255,255,255,0.15) !important;
  }
  div[data-testid="stButton"] > button[kind="primary"] {
    background: #fafafa !important;
    color: #09090B !important;
    border-color: #fafafa !important;
    font-weight: 600 !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #e4e4e7 !important;
  }

  .stTabs [data-baseweb="tab-list"] {
    gap: 0;
    background: #18181B;
    border-radius: 10px;
    padding: 3px;
    border: 1px solid rgba(255,255,255,0.07);
  }
  .stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-size: 0.8125rem;
    font-weight: 500;
    color: #71717a;
    padding: 0.45rem 0.75rem;
    flex: 1;
    justify-content: center;
  }
  .stTabs [aria-selected="true"] {
    background: #27272a !important;
    color: #fafafa !important;
  }
  .stTabs [data-baseweb="tab-highlight"] { display: none; }
  .stTabs [data-baseweb="tab-border"] { display: none; }

  div[data-testid="stExpander"] {
    background: transparent;
    border: none;
  }
  div[data-testid="stExpander"] details {
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    background: #18181B;
  }
  div[data-testid="stExpander"] summary {
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    color: #a1a1aa !important;
  }

  .stSelectbox label { display: none; }
  div[data-baseweb="select"] > div {
    background: #18181B !important;
    border-color: rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
  }

  .alt-scores {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    margin: 0.5rem 0;
  }
  .alt-score {
    font-size: 0.75rem;
    font-weight: 500;
    color: #a1a1aa;
    background: rgba(255,255,255,0.04);
    border-radius: 6px;
    padding: 0.25rem 0.5rem;
  }
  .explain {
    font-size: 0.8125rem;
    color: #a1a1aa;
    line-height: 1.55;
    margin-top: 0.5rem;
  }
</style>
"""


def inject_styles() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _esc(text: str) -> str:
    return html.escape(str(text))


def _format_date(date_str: str, short: bool = False) -> str:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d · %H:%M") if short else dt.strftime("%a %b %d · %H:%M")
    except (ValueError, TypeError):
        return date_str or "TBD"


def _is_live(status: str) -> bool:
    return status in {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"}


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
            "top_scorelines": top,
            "explanation": pred["explanation"],
            "generated_at": pred["generated_at"],
        }
    return match_dict


def _outcome_bar(h: float, d: float, a: float) -> str:
    total = h + d + a or 1
    hp, dp, ap = h / total * 100, d / total * 100, a / total * 100
    return f"""
    <div class="bar-wrap">
      <div class="bar">
        <div class="bar-h" style="width:{hp:.1f}%"></div>
        <div class="bar-d" style="width:{dp:.1f}%"></div>
        <div class="bar-a" style="width:{ap:.1f}%"></div>
      </div>
      <div class="bar-labels">
        <span class="bar-lbl">Home <strong>{h:.0%}</strong></span>
        <span class="bar-lbl">Draw <strong>{d:.0%}</strong></span>
        <span class="bar-lbl">Away <strong>{a:.0%}</strong></span>
      </div>
    </div>
    """


def render_header() -> None:
    n = len(db.get_upcoming_matches(limit=200))
    st.markdown(
        f"""
        <div class="app-header">
          <div>
            <p class="app-title">World Cup 2026</p>
            <p class="app-sub">{n} upcoming matches</p>
            <p class="app-credit">Designed by {_esc(AUTHOR)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_disclaimer_banner() -> None:
    st.markdown(
        f"""
        <div class="disclaimer-banner">
          <strong>Research only.</strong> {_esc(DISCLAIMER_SHORT)}
          Predictions are estimates, not guarantees. Not affiliated with FIFA.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    st.markdown(
        f"""
        <div class="site-footer">
          <p class="footer-credit">Designed by {_esc(AUTHOR)}</p>
          <p class="footer-disclaimer">{_esc(DISCLAIMER_FULL)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_match_card(match: dict, compact: bool = False) -> None:
    home = _esc(match.get("home_team", "?"))
    away = _esc(match.get("away_team", "?"))
    status = match.get("status", "NS")
    live = _is_live(status)
    hg, ag = match.get("home_goals"), match.get("away_goals")
    pred = match.get("prediction") or {}

    # Pick display
    top = pred.get("top_scorelines", [])
    if top:
        pick_h, pick_a = top[0]["home"], top[0]["away"]
        pick_pct = top[0]["probability"]
    elif pred:
        pick_h = int(round(pred.get("predicted_home_goals", 1)))
        pick_a = int(round(pred.get("predicted_away_goals", 1)))
        pick_pct = 0.0
    else:
        pick_h, pick_a, pick_pct = "–", "–", 0.0

    live_tag = '<span class="dot-live">●</span>LIVE · ' if live else ""
    card_cls = "card live" if live else "card"

    if hg is not None and ag is not None:
        center = f"{hg}–{ag}"
        pick_label = "Score"
    else:
        center = f"{pick_h}–{pick_a}"
        pick_label = "Pick"

    st.markdown(
        f"""
        <div class="{card_cls}">
          <div class="card-time">{live_tag}{_esc(_format_date(match.get('date', ''), short=True))}</div>
          <div class="matchup">
            <div class="team left">{home}</div>
            <div class="pick-badge">
              <div class="pick-score">{center}</div>
              <div class="pick-label">{pick_label}</div>
              {f'<div class="pick-conf">{pick_pct:.0%} likely</div>' if pick_pct and not compact else ''}
            </div>
            <div class="team right">{away}</div>
          </div>
        """,
        unsafe_allow_html=True,
    )

    if pred and not compact:
        h, d, a = pred.get("home_win_prob", 0), pred.get("draw_prob", 0), pred.get("away_win_prob", 0)
        st.markdown(_outcome_bar(h, d, a), unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if pred and not compact and (len(top) > 1 or pred.get("explanation")):
        with st.expander("Why this score?"):
            if len(top) > 1:
                alts = "".join(
                    f'<span class="alt-score">{s["home"]}–{s["away"]} · {s["probability"]:.0%}</span>'
                    for s in top[1:5]
                )
                st.markdown(
                    f'<p style="font-size:0.75rem;color:#71717a;margin:0 0 0.25rem">Other likely scores</p>'
                    f'<div class="alt-scores">{alts}</div>',
                    unsafe_allow_html=True,
                )
            if pred.get("explanation"):
                st.markdown(
                    f'<p class="explain">{_esc(pred["explanation"])}</p>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<p class="pick-disclaimer">{_esc(DISCLAIMER_SHORT)}</p>',
                unsafe_allow_html=True,
            )


def render_toolbar() -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Refresh", use_container_width=True, type="primary"):
            with st.spinner("Syncing…"):
                sync_all_matches()
                generate_predictions()
            st.rerun()
    with c2:
        if st.button("Live", use_container_width=True):
            with st.spinner("…"):
                sync_live_data()
            st.rerun()
    with c3:
        with st.popover("More"):
            if st.button("Sync injuries", use_container_width=True):
                sync_injuries()
                st.rerun()
            if st.button("Retrain model", use_container_width=True):
                retrain_and_predict()
                st.rerun()


def _auto_bootstrap() -> None:
    if st.session_state.get("bootstrapped"):
        return
    st.session_state["bootstrapped"] = True
    if len(db.get_upcoming_matches(limit=1)) == 0:
        try:
            from src.sync_historical import sync_historical_seasons
            sync_historical_seasons()
            sync_all_matches()
            generate_predictions()
        except Exception:
            pass


def page_upcoming() -> None:
    matches = [_attach_prediction(_row_to_dict(m)) for m in db.get_upcoming_matches()]
    if not matches:
        st.markdown('<div class="empty">No matches yet.<br>Tap <strong>Refresh</strong> above.</div>', unsafe_allow_html=True)
        return
    for m in matches:
        render_match_card(m)


def page_live() -> None:
    matches = [_attach_prediction(_row_to_dict(m)) for m in db.get_live_matches()]
    if not matches:
        st.markdown('<div class="empty">No live matches right now.</div>', unsafe_allow_html=True)
        return
    for m in matches:
        render_match_card(m)


def page_results() -> None:
    matches = [_row_to_dict(m) for m in db.get_recent_matches(limit=40)]
    if not matches:
        st.markdown('<div class="empty">No results yet.</div>', unsafe_allow_html=True)
        return
    rows = ""
    for m in matches:
        hg = m.get("home_goals", "–")
        ag = m.get("away_goals", "–")
        rows += f"""
        <div class="result">
          <div class="result-info">
            <div class="result-teams">{_esc(m['home_team'])} vs {_esc(m['away_team'])}</div>
            <div class="result-date">{_esc(_format_date(m['date'], short=True))}</div>
          </div>
          <div class="result-score">{hg}–{ag}</div>
        </div>
        """
    st.markdown(f'<div class="card" style="padding:0 1.125rem">{rows}</div>', unsafe_allow_html=True)


def page_detail() -> None:
    upcoming = db.get_upcoming_matches(limit=100)
    recent = db.get_recent_matches(limit=50)
    all_matches = list(upcoming) + list(recent)
    if not all_matches:
        st.markdown('<div class="empty">No matches available.</div>', unsafe_allow_html=True)
        return

    options = {f"{m['home_team']} vs {m['away_team']}": int(m["id"]) for m in all_matches}
    selected = st.selectbox("Match", list(options.keys()), label_visibility="collapsed")
    match = _attach_prediction(_row_to_dict(db.get_match_by_id(options[selected])))
    render_match_card(match)

    injuries = db.get_injuries_for_teams([match["home_team"], match["away_team"]])
    lineups = db.get_lineups(int(match["id"]))

    if injuries or lineups:
        with st.expander("Squad info"):
            if injuries:
                st.markdown("**Injuries**")
                for i in injuries:
                    st.caption(f"{i['player_name']} ({i['team']}) — {i.get('reason') or 'Out'}")
            if lineups:
                for team in {r["team"] for r in lineups}:
                    starters = [r["player_name"] for r in lineups if r["team"] == team and r["is_starting"]]
                    if starters:
                        st.markdown(f"**{team}**")
                        st.caption(", ".join(starters[:11]))


def main() -> None:
    inject_styles()
    _auto_bootstrap()
    render_header()
    render_disclaimer_banner()
    render_toolbar()

    tab1, tab2, tab3, tab4 = st.tabs(["Matches", "Live", "Results", "Detail"])

    with tab1:
        page_upcoming()
    with tab2:
        page_live()
    with tab3:
        page_results()
    with tab4:
        page_detail()

    render_footer()


if __name__ == "__main__":
    main()
