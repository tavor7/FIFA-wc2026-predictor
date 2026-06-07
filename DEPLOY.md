# Render.com deployment — https://fifa-wc2026-predictor.onrender.com (your URL will differ)

> **Research only.** Designed by **Amit Tavor**. For educational use — not betting advice. See [DISCLAIMER.md](DISCLAIMER.md).

Deploy the app so it works on your phone from anywhere, not only on local WiFi.

Repo: [github.com/tavor7/FIFA-wc2026-predictor](https://github.com/tavor7/FIFA-wc2026-predictor)

---

## Option A — Blueprint (easiest)

1. Go to [dashboard.render.com](https://dashboard.render.com) and sign in with **GitHub**.
2. Click **New +** → **Blueprint**.
3. Connect repo **`tavor7/FIFA-wc2026-predictor`**.
4. Render detects `render.yaml` — click **Apply**.
5. When prompted, set these **secret** environment variables:
   - `API_FOOTBALL_KEY` — from your local `.env`
   - `FOOTBALL_DATA_KEY` — from your local `.env`
6. Wait 5–10 minutes for the first deploy.

---

## Option B — Manual Web Service

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Web Service**.
2. Connect **`tavor7/FIFA-wc2026-predictor`**.
3. Settings:

| Field | Value |
|-------|--------|
| **Name** | `fifa-wc2026-predictor` |
| **Region** | closest to you |
| **Branch** | `main` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false` |
| **Plan** | Free |

4. **Environment** → add variables:

| Key | Value |
|-----|--------|
| `PYTHON_VERSION` | `3.11.9` |
| `API_FOOTBALL_KEY` | your key |
| `FOOTBALL_DATA_KEY` | your key |
| `LEAGUE_ID` | `1` |
| `SEASON` | `2026` |
| `FOOTBALL_DATA_COMPETITION_ID` | `2000` |
| `DB_PATH` | `data/football.db` |

5. Click **Create Web Service**.

---

## After deploy

1. Open your Render URL on your phone (e.g. `https://fifa-wc2026-predictor.onrender.com`).
2. **First visit may take 30–60s** — free tier wakes from sleep.
3. If matches are empty: **Sync & update data → Sync matches → Generate picks**.
4. Bookmark or **Add to Home Screen** on your phone.

---

## Updating the app

```bash
cd /Users/amit/Desktop/AMIT/DataScience/S8/FIFA/football_research_predictor
git add .
git commit -m "Update app"
git push
```

Render redeploys automatically on each push to `main`.

---

## Free tier notes

| Topic | Detail |
|-------|--------|
| **Cost** | Free web service |
| **Sleep** | App sleeps after ~15 min idle; first load after sleep is slow |
| **API keys** | Set in Render **Environment**, never in GitHub |
| **Database** | SQLite resets on redeploy; app auto-syncs on first visit |
| **Custom domain** | Optional in Render settings |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **Deploy failed** | Check Render logs → ensure `requirements.txt` installs cleanly |
| **502 / not loading** | Wait 60s (cold start); check Start Command uses `$PORT` |
| **No matches** | Verify `FOOTBALL_DATA_KEY` in Environment; tap Sync matches |
| **Module not found** | Ensure repo root has `app.py` and `src/` folder |

---

## Local development

```bash
source .venv/bin/activate
streamlit run app.py
```
