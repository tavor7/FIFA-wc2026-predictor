# Football Research Predictor

**Designed by Amit Tavor**

A Python research tool for tracking FIFA World Cup matches, syncing live data from football APIs, and generating **probability-based score predictions with explanations**.

> **Disclaimer — read before use**
>
> This project is for **educational and research purposes only**. It is **not** betting advice, gambling advice, or financial advice. All outputs are probabilistic estimates — not guaranteed predictions. This tool is **not affiliated with FIFA** or any official football organization. No betting odds, gambling APIs, or wagering recommendations are integrated. **Use at your own discretion.**

## Features

- Sync upcoming and recent matches from **API-Football v3** (with **football-data.org** fallback)
- Live score, statistics, lineups, and injury updates
- Feature engineering from form, goals, injuries, lineups, and discipline
- Random Forest expected-goals model with **Poisson scoreline distributions**
- Deterministic, template-based prediction explanations (no LLM)
- Streamlit dashboard for exploration

## Requirements

- Python 3.11+
- API keys (free tiers available):
  - [API-Football](https://www.api-football.com/) — primary data source
  - [football-data.org](https://www.football-data.org/) — optional fallback

## Installation

```bash
cd football_research_predictor
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
API_FOOTBALL_KEY=your_key_here
FOOTBALL_DATA_KEY=your_key_here
LEAGUE_ID=1        # FIFA World Cup
SEASON=2026
DB_PATH=data/football.db
```

## Run on your phone (remote)

Deploy on **[Render](https://render.com)** for a public URL that works anywhere.

Repo: [github.com/tavor7/FIFA-wc2026-predictor](https://github.com/tavor7/FIFA-wc2026-predictor)

**Quick steps:**

1. Go to [dashboard.render.com](https://dashboard.render.com) → sign in with GitHub.
2. **New +** → **Blueprint** → select `tavor7/FIFA-wc2026-predictor`.
3. Set secret env vars: `API_FOOTBALL_KEY`, `FOOTBALL_DATA_KEY` (from your `.env`).
4. Deploy → open the Render URL on your phone.

Full instructions: see **[DEPLOY.md](DEPLOY.md)**.

> Free tier sleeps when idle; first load after sleep may take ~30–60s. The app auto-syncs fixtures on first visit.

## Local development

```bash
streamlit run app.py
```

Open the URL shown in the terminal (typically `http://localhost:8501`).

## Dashboard Actions

| Button | Action |
|--------|--------|
| Sync upcoming matches | Fetch upcoming + recent fixtures |
| Sync live data now | Update live scores, stats, lineups |
| Sync injuries now | Refresh injury reports |
| Generate predictions | Build Poisson scoreline probabilities |
| Retrain model | Train Random Forest on finished matches |

## Optional Background Scheduler

Run automatic sync jobs (matches every 6h, injuries every 3h, live every 60s):

```bash
python -m src.scheduler
```

## Project Structure

```
football_research_predictor/
├── app.py                  # Streamlit dashboard
├── requirements.txt
├── .env.example
├── README.md
├── data/
│   └── football.db         # SQLite database (created on first run)
└── src/
    ├── config.py           # Environment configuration
    ├── db.py               # SQLite schema and queries
    ├── api_client.py       # API-Football + fallback client
    ├── sync_matches.py     # Match sync
    ├── sync_live_data.py   # Live data polling
    ├── sync_injuries.py    # Injury sync
    ├── sync_players.py     # Player/squad sync
    ├── features.py         # Feature engineering
    ├── model.py            # ML model + Poisson distribution
    ├── predict.py          # Prediction pipeline
    ├── explain.py          # Template explanations
    └── scheduler.py        # Background jobs
```

## Scoring Context (Friend League Game)

This tool helps inform predictions for friend-group scoring games where:

- **Group stage:** exact score = base points + 4 bonus; correct outcome = base points
- **Knockout:** base points doubled; exact score adds +6 bonus
- **Tournament winner / top scorer:** long-term bonus selections

Use the probability outputs to choose scorelines with the best expected value for *your* league's scoring rules — the app itself does not optimize for any specific scoring system.

## Data Sources

| Source | Used For |
|--------|----------|
| API-Football v3 | Fixtures, live scores, stats, events, lineups, injuries, players |
| football-data.org | Fallback fixtures and results |

## Limitations

- Predictions depend on available historical and live data
- Early in a tournament, the model falls back to heuristics until enough finished matches exist
- API rate limits apply on free tiers
- No betting or odds data is used or recommended

## License

Educational use. Respect API provider terms of service.
