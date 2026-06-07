# Supabase setup

Persistent Postgres database for Render + Expo. Designed by **Amit Tavor**.

## Step 1 — Create Supabase project

1. Go to [supabase.com](https://supabase.com) → **Start your project**
2. Create a new project (free tier is fine)
3. Choose a region close to your Render region
4. Save your database password

## Step 2 — Run the schema

1. In Supabase dashboard → **SQL Editor** → **New query**
2. Copy/paste the contents of [`schema.sql`](./schema.sql)
3. Click **Run**

You should see “Success” with tables: `matches`, `predictions`, `injuries`, etc.

## Step 3 — Get connection string

1. **Project Settings** → **Database**
2. Under **Connection string**, choose **URI**
3. Select **Transaction pooler** (recommended for Render) or **Direct connection**
4. Copy the URL — it looks like:

```
postgresql://postgres.xxxxx:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

Replace `[YOUR-PASSWORD]` with your actual database password.

## Step 4 — Add to Render

1. [dashboard.render.com](https://dashboard.render.com) → your API service → **Environment**
2. Add:

| Key | Value |
|-----|--------|
| `DATABASE_URL` | your Supabase connection string |

3. **Save Changes** → Render redeploys

## Step 5 — Verify

Open: `https://YOUR-API.onrender.com/health`

You should see:

```json
{
  "status": "ok",
  "database": "supabase_postgres",
  ...
}
```

Then call bootstrap once:

```bash
curl -X POST https://YOUR-API.onrender.com/bootstrap
```

Pull to refresh in the Expo app.

## Local development

**Without Supabase** — uses SQLite automatically (leave `DATABASE_URL` empty):

```bash
uvicorn api_server:app --reload --port 8000
```

**With Supabase locally** — add to `.env`:

```env
DATABASE_URL=postgresql://postgres.xxxxx:password@...pooler.supabase.com:6543/postgres
```

## Notes

| Topic | Detail |
|-------|--------|
| Cost | Supabase free tier: 500 MB, enough for this project |
| Security | Never commit `DATABASE_URL` — use Render env vars only |
| Pooler | Use port **6543** (pooler) on Render, not 5432 direct |
| SQLite | Still works locally when `DATABASE_URL` is unset |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `connection refused` | Check password in URL, use pooler string |
| `relation does not exist` | Run `schema.sql` in Supabase SQL Editor |
| `database: sqlite` on Render | `DATABASE_URL` not set in Render env |
| SSL errors | Add `?sslmode=require` to connection string if needed |
