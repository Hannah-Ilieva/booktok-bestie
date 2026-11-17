import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def database_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env")
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is not set. Run setup.ps1 and start the local database.")
    return value


def connect() -> psycopg.Connection:
    return psycopg.connect(
        database_url(),
        connect_timeout=4,
        row_factory=dict_row,
    )


def database_ready() -> bool:
    try:
        with connect() as connection:
            connection.execute("SELECT 1")
        return True
    except (psycopg.Error, RuntimeError):
        return False


def schema_status() -> tuple[bool, str]:
    try:
        with connect() as connection:
            applied = connection.execute(
                "SELECT version FROM app_schema_migrations"
            ).fetchall()
        versions = {row["version"] for row in applied}
        required = "002_shelf_search_and_reviews.sql"
        if required not in versions:
            return False, "The PostgreSQL catalog migrations have not been applied yet."
        return True, "Local PostgreSQL and the catalog schema are ready."
    except RuntimeError as exc:
        return False, str(exc)
    except psycopg.Error:
        return False, "PostgreSQL is unavailable or its migrations have not been applied."
