# Deploy remotely (Streamlit Cloud)

Your app will get a public URL like `https://wc2026-predictor.streamlit.app` that works on any phone, anywhere.

## Step 1 — Create a GitHub account & repo

1. Go to [github.com](https://github.com) and sign in (or create an account).
2. Click **+ → New repository**.
3. Name it e.g. `wc2026-predictor`.
4. Leave it **Public** (required for free Streamlit Cloud).
5. Do **not** add README or .gitignore (you already have them).
6. Click **Create repository**.

## Step 2 — Push your code

Run these in Terminal (replace `YOUR_USERNAME`):

```bash
cd /Users/amit/Desktop/AMIT/DataScience/S8/FIFA/football_research_predictor

git init
git add .
git commit -m "WC 2026 predictor app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/wc2026-predictor.git
git push -u origin main
```

> Your `.env` file is **not** uploaded (it's in `.gitignore`). API keys go in Step 4.

## Step 3 — Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io).
2. Sign in with **GitHub**.
3. Click **Create app**.
4. Choose your repo `wc2026-predictor`.
5. Set **Main file path** to: `app.py`
6. Click **Advanced settings** → open **Secrets**.
7. Paste this (use your real keys from `.env`):

```toml
API_FOOTBALL_KEY = "paste_your_api_football_key"
FOOTBALL_DATA_KEY = "paste_your_football_data_key"
LEAGUE_ID = "1"
SEASON = "2026"
FOOTBALL_DATA_COMPETITION_ID = "2000"
DB_PATH = "data/football.db"
```

8. Click **Deploy**.

Wait 2–3 minutes. You'll get a live URL — open it on your phone and add to home screen.

## Step 4 — After deploy

- First load may take ~30s while it syncs fixtures automatically.
- Tap **Sync & update data → Sync matches** if the list is empty.
- Tap **Generate picks** to refresh predictions.

## Updating the app later

```bash
git add .
git commit -m "Update app"
git push
```

Streamlit Cloud redeploys automatically on each push.

## Important notes

| Topic | Detail |
|-------|--------|
| Cost | Free on Streamlit Community Cloud |
| API keys | Stored in Streamlit Secrets, never in GitHub |
| Database | Resets on cold start; app auto-syncs on first visit |
| Model | Uses heuristics until you tap **Retrain model** with enough finished matches |

## Troubleshooting

- **App crashes on start** — check Secrets format (TOML, quoted strings).
- **No matches** — verify `FOOTBALL_DATA_KEY` in Secrets; tap Sync matches.
- **Deploy failed** — ensure `app.py` is at repo root and `requirements.txt` exists.
