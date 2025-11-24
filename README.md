# VirtualFlex Smart AI desk system — Flask + OpenAI demo

This is a minimal Flask prototype for an AI-driven help desk ticket triage system. It accepts user-submitted tickets, calls the OpenAI API to classify category and priority, and stores tickets in SQLite.

Quickstart

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.

2. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Run the app:

```powershell
python app.py
```

4. Open `http://127.0.0.1:5000/submit` to submit a ticket.

Recent updates (2025-11-15)
---------------------------
- Added a friendly CSRF error handler to avoid exposing debug stack traces and file paths on invalid/missing CSRF tokens.
- Added basic server-side logging for failed admin login attempts and CSRF failures to aid diagnostics.
- Fixed an admin dashboard template issue by computing "Recent (Today)" ticket counts server-side to avoid template runtime errors.
- Note: The development server runs with `debug=True` by default for local development. Do NOT expose the debug server in production — set `FLASK_ENV=production` and run under a WSGI server (gunicorn/uvicorn) instead.

Admin

- There is a simple admin login available at `/admin/login`. Set `ADMIN_PASSWORD` in your `.env` file (default is `admin`). After login you can visit `/admin` to edit tickets and log corrections.
 - There is a simple admin login available at `/admin/login`.
	- For security you can set `ADMIN_PASSWORD_HASH` in your `.env` (recommended). If only `ADMIN_PASSWORD` is present the app will derive a runtime hash from it. Example (recommended):

```text
ADMIN_PASSWORD_HASH=pbkdf2:sha256:150000$...yourhash...
```

	- Session lifetime is controlled by `SESSION_HOURS` (default 1 hour). To change the plain-text password (development only) set `ADMIN_PASSWORD` in `.env`.

Testing & CI

- Unit tests use `pytest`. Run tests locally:

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
```

Docker

- Build and run with Docker Compose:

```powershell
docker-compose up --build
```
