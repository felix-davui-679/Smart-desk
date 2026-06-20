# VirtualFlex Smart AI desk system — Flask + OpenAI demo

This is a minimal Flask prototype for an AI-driven help desk ticket triage system. It accepts user-submitted tickets, calls the OpenAI API to classify category and priority, and stores tickets in SQLite.

## Quickstart

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` (and the admin/secret values below).

2. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Run the app (development):

```powershell
python app.py
```

4. Open `http://127.0.0.1:5000/submit` to submit a ticket.

## Configuration

The app is configured entirely through environment variables (see `.env.example`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI API key for classification | _(falls back to keyword heuristics if unset)_ |
| `OPENAI_MODEL` | Chat model used for classification | `gpt-4o-mini` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///tickets.db` |
| `FLASK_SECRET` | Flask session signing key — **required in production** | _(random per-process in dev)_ |
| `ADMIN_PASSWORD_HASH` | Werkzeug hash for the admin login (recommended) | — |
| `ADMIN_PASSWORD` | Plain admin password (dev only; hashed at runtime) | — |
| `SESSION_HOURS` | Admin session lifetime | `1` |
| `FLASK_ENV` | Set to `production` to disable the debug server | — |
| `PORT` | Port to bind | `5000` |

## Admin

- There is a simple admin login at `/admin/login`. After login you can visit `/admin` to edit tickets and log corrections.
- For security, set `ADMIN_PASSWORD_HASH` in your `.env` (recommended). If only `ADMIN_PASSWORD` is present the app derives a runtime hash from it. Generate a hash with:

```powershell
python scripts/make_admin_hash.py
```

```text
ADMIN_PASSWORD_HASH=pbkdf2:sha256:260000$...yourhash...
```

- Session lifetime is controlled by `SESSION_HOURS` (default 1 hour).

## Production notes

- **Do not run the built-in development server in production.** `python app.py` only enables the Werkzeug debug server when `FLASK_ENV` is _not_ `production`. In production, run under a WSGI server (the provided Docker image uses gunicorn).
- `FLASK_SECRET` **must** be set in production; otherwise sessions use an ephemeral per-process key and will not survive a restart or scale across workers.
- A friendly CSRF error handler avoids exposing debug stack traces on invalid/missing CSRF tokens, and failed admin logins / CSRF failures are logged server-side for diagnostics.

## Testing & CI

Unit tests use `pytest`. Run tests locally:

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
```

CI runs the suite on every push/PR via GitHub Actions (`.github/workflows/ci.yml`).

## Docker

Build and run with Docker Compose (serves via gunicorn):

```powershell
docker-compose up --build
```
