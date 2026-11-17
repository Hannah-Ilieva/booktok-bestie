# BookTok Bestie

A local, single-user book tracker and discovery app built with Streamlit, SQLite, PostgreSQL, pgvector, and optional local Sentence Transformers. No hosting, accounts, or multi-user authentication are included.

## Keep your existing shelf safe

The original `app.py` and `database.py` remain the SQLite tracker. The new discovery app is `discovery_app.py`, and its pages live in `app_pages/`. The SQLite file `booktok.db` remains in place. The import script opens it read-only, creates a verified backup, and skips shelf IDs already imported into PostgreSQL.

The initial catalog setup has two migrations under `migrations/`. They create provider provenance, work/edition records, reader shelf data, editable label taxonomy and correction history, fuzzy-match review, interaction events, and 384-dimensional vector storage.

## One-command Windows setup

Install Python 3.10 or newer with the Python Launcher (`py`). To install the full app, including the optional local ML dependencies, run this one terminal command from the project folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -WithML
```

The script creates or reuses `.venv`, installs dependencies, and creates an ignored `.env` with a random local database password if there is no `.env` yet. Sentence Transformer model weights download the first time you embed or search. The setup does not start Docker or change `booktok.db`.

## Start PostgreSQL and import your shelf

Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/), open it, and wait until Docker reports that it is running. Docker Desktop includes Docker Compose. Then run these commands from the project folder:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe -m scripts.apply_migrations
.\.venv\Scripts\python.exe -m scripts.backup_sqlite
.\.venv\Scripts\python.exe -m scripts.migrate_sqlite_to_postgres
```

The import creates another timestamped backup, uses SQLite's online backup API, and opens the original database read-only. It retains every shelf row, review, rating, progress value, and timestamp. It does not merge duplicate titles. Copy a backup from `backups/` somewhere outside the project before relying on PostgreSQL as your only working shelf.

Check the service with `docker compose ps`; it should report `healthy`. Stop it with `docker compose stop db`. The named volume remains in place. Avoid `docker compose down -v` if you want to keep the local catalog.

## Run the apps

The original tracker remains available at any time:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

After PostgreSQL is healthy and the SQLite shelf is imported, start the new app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run discovery_app.py
```

The new app provides Discover, My Shelf, Recommendations, Reading Stats, Labels and Review, and Local Setup pages. It uses a parchment/ivory/plum theme with serif headings. If PostgreSQL or the migrations are unavailable, it shows setup instructions; the original SQLite app remains usable.

## Search and metadata providers

Open Library and Google Books are available for small on-demand searches. Hardcover is optional and requires a personal token from [Hardcover API settings](https://hardcover.app/account/api). Add optional credentials to the ignored `.env` file and restart Streamlit:

```text
GOOGLE_BOOKS_API_KEY=
HARDCOVER_API_TOKEN=
```

Searches run only when submitted. Each result keeps its provider ID and source link. Exact provider IDs and ISBNs deduplicate automatically; uncertain title matches appear in the review queue instead of being merged automatically. You can also run one small provider ingestion from the terminal:

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_provider --provider open_library --query "cozy fantasy romance" --limit 10
```

## Local machine-learning jobs

The local `sentence-transformers/all-MiniLM-L6-v2` model creates description embeddings for pgvector and semantic query vectors. It runs on CPU and keeps model files under ignored `.model-cache/`. Embedding and classification jobs are manually invoked; they do not run on Streamlit reruns:

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_embeddings --limit 250
.\.venv\Scripts\python.exe -m scripts.classify_catalog --limit 100
```

Genre, trope, and theme suggestions use description-to-label similarity. Spice labels only use explicit source-text cues because spice is subjective. Suggestions include a model/version and similarity or cue score, remain unverified until reviewed, and can be left unknown. The score is not a calibrated probability and is not an accuracy claim. The Labels and Review page lets you edit the taxonomy, correct labels, retain correction history, and review possible duplicate works.

Recommendations use a transparent baseline combining semantic similarity, selected label overlap, and signals from ratings, saved books, clicks, and skips. Each card shows its reasons, ordering score, component values, and active weights; the score is not a probability. XGBoost training is not enabled; it should wait for enough human-reviewed interaction data.
