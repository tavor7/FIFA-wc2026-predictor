# Deploy remotely (Render + Expo)

> **Research only.** Designed by **Amit Tavor**. See [DISCLAIMER.md](DISCLAIMER.md).

Architecture:

```
Phone (Expo app)  →  Render (FastAPI API)  →  SQLite + football APIs
```

---

## Step 1 — Deploy the API on Render

Repo: [github.com/tavor7/FIFA-wc2026-predictor](https://github.com/tavor7/FIFA-wc2026-predictor)

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**
2. Select your repo (uses `render.yaml`)
3. Set secret env vars: `API_FOOTBALL_KEY`, `FOOTBALL_DATA_KEY`
4. Deploy → copy your API URL, e.g. `https://fifa-wc2026-api.onrender.com`

Test: open `https://YOUR-API.onrender.com/health`

> If you already deployed Streamlit on Render, **update the Start Command** to:
> `uvicorn api_server:app --host 0.0.0.0 --port $PORT`

---

## Step 2 — Run Expo on your phone

```bash
cd mobile
npm install
cp .env.example .env
```

Edit `.env`:

```env
EXPO_PUBLIC_API_URL=https://fifa-wc2026-api.onrender.com
```

Start:

```bash
npm start
```

Scan QR with **Expo Go** — works from anywhere, not just local WiFi.

---

## Step 3 — Pull to refresh

On the **Matches** tab, pull down to sync fixtures and regenerate predictions.

---

## Optional — Standalone app (no Expo Go)

```bash
cd mobile
npx eas build --platform ios    # or android
```

Requires free [expo.dev](https://expo.dev) account.

---

## Local development

**Terminal 1 — API:**
```bash
uvicorn api_server:app --reload --port 8000
```

**Terminal 2 — Expo:**
```bash
cd mobile && npm start
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| App can't connect | Check `EXPO_PUBLIC_API_URL` in `mobile/.env` |
| API 502 / slow | Render free tier cold start — wait 60s |
| Empty matches | Open API `/bootstrap` or pull to refresh in app |
| Streamlit still running | Render now uses FastAPI; redeploy from latest `render.yaml` |
