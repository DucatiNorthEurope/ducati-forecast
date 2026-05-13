# Ducati Forecast Portal

Two halves of the same job, deployed together on Vercel:

- **`/`** — Ross's *Forecast Submission Portal* (`index.html`). Dealers submit their weekly forecast; data goes to Google Sheets via Apps Script.
- **`/dashboard`** — *Availability Dashboard* (Flask app under `app/`). Dealers see what's currently expected per model × month, with a per-dealer password; admin manages mappings, embargoes and dealer logins.

## Local dev

```
cd app
./run.sh
```

First launch creates a venv, installs `requirements.txt` (from the project root), and starts the server on <http://127.0.0.1:5050>. The local DB is a SQLite file at `app/data/dashboard.db`. Default admin password: `admin` — change it from Admin → Dealers.

Set `URL_PREFIX=/dashboard` to test the prefixed-mount mode that Vercel uses.

## Deploy to Vercel

1. Sign in to [vercel.com](https://vercel.com) and import this repo. Vercel auto-detects the Python runtime via `requirements.txt` and `api/index.py`.
2. Add a Postgres database: Vercel project → **Storage → Create → Postgres** (Hobby tier is free). Vercel automatically sets `DATABASE_URL` for you.
3. Set environment variables (Project → Settings → Environment Variables):
   - `ADMIN_PASSWORD` — pick something non-trivial. This is used the first time the database is initialised; after that, change via the admin UI.
4. **Redeploy** so the env vars take effect.

The first time the app runs against the new Postgres DB, it creates the schema and seeds the 37 Material-prefix → plan-model rows. Log in as admin, upload the plan + orders xlsx files via Admin → Upload, and you're live.

## What's in the repo

```
/
├── index.html              Ross's static portal (Google Sheets backend)
├── api/
│   └── index.py            Vercel function entry — mounts Flask under /dashboard
├── app/
│   ├── __init__.py
│   ├── app.py              Flask routes + WSGI prefix middleware
│   ├── db.py               SQLite (local) / Postgres (prod) layer
│   ├── parsers.py          xlsx → rows (operates on file streams)
│   ├── seed_data.py        37 initial material-prefix → plan-model rows
│   ├── templates/          Jinja templates
│   ├── data/               SQLite + uploads (gitignored, local-only)
│   └── run.sh
├── requirements.txt
├── vercel.json
└── README.md
```

## Backups

- **Local**: copy `app/data/dashboard.db` somewhere safe.
- **Vercel Postgres**: the Vercel dashboard has a "Backups" tab; daily snapshots on paid plans, manual export from the dashboard otherwise.
