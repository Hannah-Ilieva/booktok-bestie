# BookTok Bestie

![BookTok Bestie — a local reading tracker and book discovery app](assets/booktok-bestie-banner.svg)

A local-first reading tracker and book discovery app. Keep your shelf on your computer, find books across metadata providers, and get transparent recommendations.

## Features

- Track reading status, progress, ratings, reviews, and stats.
- Search Open Library and Google Books; optionally enable Hardcover.
- Use local semantic search and unverified genre, trope, theme, and spice suggestions.
- Review labels and possible duplicate records before they affect recommendations.
- Keep the original SQLite app and import its shelf into the local PostgreSQL catalog when ready.

## Install

On Windows, install Python 3.10+ and Docker Desktop. From the project folder, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -WithML
```

This creates `.venv` and a private, ignored `.env`. Start Docker Desktop, then initialize the local catalog and import your shelf:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe -m scripts.apply_migrations
.\.venv\Scripts\python.exe -m scripts.migrate_sqlite_to_postgres
```

The importer makes a backup, reads `booktok.db` without writing to it, and skips rows already imported. The PostgreSQL database uses a persistent Docker volume; avoid `docker compose down -v` to keep it.

Launch the new app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run discovery_app.py
```

The original SQLite tracker remains available with `streamlit run app.py`.

## Local ML and providers

The optional local Sentence Transformer runs on CPU. Its model downloads on first use and stays under the ignored `.model-cache/` directory. Create embeddings and label suggestions on demand:

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_embeddings --limit 250
.\.venv\Scripts\python.exe -m scripts.classify_catalog --limit 100
```

Suggestions remain unverified until you review them. Spice uses explicit text cues; similarity scores are not probabilities. Recommendations show their reasons and active score weights. Supervised ranking is deferred until there is enough reviewed feedback.

Open Library and Google Books searches need no credentials. Add `GOOGLE_BOOKS_API_KEY` or `HARDCOVER_API_TOKEN` to `.env` to enable those optional provider settings, then restart the app. Searches run only when submitted.

## License

[MIT](LICENSE)
