# BookTok Bestie

A local, single-user book tracker and discovery project built with Python, Streamlit, and SQLite. The existing shelf remains in `booktok.db`; setup does not replace or migrate it.

## Current project shape

- `app.py` is the Streamlit interface.
- `database.py` reads and writes the existing SQLite shelf.
- `recommendations.py` contains the current mood and trope recommender.
- `migrations/001_catalog.sql` is the initial PostgreSQL catalog schema, including provider provenance, label review history, interaction events, and pgvector support.
- `docker-compose.yml` prepares a local PostgreSQL 17 database with pgvector. The app still uses SQLite until the catalog and history migration is implemented.

The SQLite database was inspected read-only during setup work. It contains one `books` table and one saved row. No rows or files in the database were changed.

## Install on Windows

Install Python 3.10 or newer with the Python Launcher (`py`). From the project folder, run this single terminal command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

The script creates or reuses `.venv`, installs the Python requirements, and creates an ignored `.env` file with a random local database password if one does not already exist. It does not start Docker or alter `booktok.db`.

Start the current app with:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Optional local PostgreSQL

Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/), open it, and wait until Docker reports that it is running. Docker Desktop includes Docker Compose. Then, from the project folder, start the database:

```powershell
docker compose up -d db
```

Apply the catalog schema with:

```powershell
.\.venv\Scripts\python.exe .\scripts\apply_migrations.py
```

Check the service with `docker compose ps`. Stop it with `docker compose stop db`; the named data volume remains in place. The Streamlit app does not use PostgreSQL yet, so the existing shelf continues to be stored in SQLite.

## Back up the SQLite shelf

Before any future SQLite-to-PostgreSQL import, create a verified backup:

```powershell
.\.venv\Scripts\python.exe .\scripts\backup_sqlite.py
```

The script uses SQLite's online backup API, opens the source read-only, checks the copy, and writes a timestamped file under the ignored `backups/` folder. Keep a copy of that backup somewhere outside the project before proceeding with a data import.

## Manual run-through

1. Run the one-command setup above and confirm it finishes with “BookTok Bestie dependencies are installed.”
2. Start Streamlit and confirm the app opens at the local address printed in the terminal.
3. Confirm your existing shelf row and reading stats still appear.
4. If you have installed Docker Desktop, start the database and confirm `docker compose ps` shows `db` as healthy.
5. Run the backup command and confirm a new timestamped file appears in `backups/`.

No automated tests are included in this setup step. The PostgreSQL database and the existing SQLite shelf remain separate until a reviewed import command is added.
