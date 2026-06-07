# Deploy remotely (Render + Expo)

> **Research only.** Designed by **Amit Tavor**. See [DISCLAIMER.md](DISCLAIMER.md).

Architecture:

```
Phone (Expo app)  →  Render (FastAPI API)  →  Supabase Postgres + football APIs
```

---

## Step 1 — Set up Supabase (database)

Full guide: **[supabase/README.md](supabase/README.md)**

1. Create a free project at [supabase.com](https://supabase.com)
2. **SQL Editor** → run [`supabase/schema.sql`](supabase/schema.sql)
3. **Project Settings → Database** → copy **Connection string** (URI, pooler port 6543)
4. Save it — you'll add it to Render as `DATABASE_URL`

---

## Step 2 — Deploy the API on Render

Repo: [github.com/tavor7/FIFA-wc2026-predictor](https://github.com/tavor7/FIFA-wc2026-predictor)

1. [dashboard.render.com](https://dashboard.render.com) → your service → **Environment**
2. Add env vars:

| Key | Value |
|-----|--------|
| `API_FOOTBALL_KEY` | your key |
| `FOOTBALL_DATA_KEY` | your key |
| `DATABASE_URL` | Supabase connection string |

3. **Start Command:** `uvicorn api_server:app --host 0.0.0.0 --port $PORT`
4. Deploy → copy API URL

Test: `https://YOUR-API.onrender.com/health` should show `"database": "supabase_postgres"`

Then bootstrap once:

```bash
curl -X POST https://YOUR-API.onrender.com/bootstrap
```

---

## Step 3 — Run Expo on your phone

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
| App can't connect | Check `EXPO_PUBLIC_API_URL` in the project root `.env` |
| API 502 / slow | Render free tier cold start — wait 60s |
| Empty matches | Open API `/bootstrap` or pull to refresh in app |
| Streamlit still running | Render now uses FastAPI; redeploy from latest `render.yaml` |
