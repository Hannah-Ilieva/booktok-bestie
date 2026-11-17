from hashlib import sha256
import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is missing. Run setup.ps1 and check the local .env file.")

    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    if not migration_files:
        raise SystemExit(f"No SQL migrations found in {MIGRATIONS_DIR}")

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        for migration_path in migration_files:
            sql = migration_path.read_text(encoding="utf-8")
            checksum = sha256(sql.encode("utf-8")).hexdigest()
            row = connection.execute(
                "SELECT checksum FROM app_schema_migrations WHERE version = %s",
                (migration_path.name,),
            ).fetchone()

            if row:
                if row[0] != checksum:
                    raise SystemExit(
                        f"{migration_path.name} has changed since it was applied. "
                        "Add a new numbered migration instead of editing an applied file."
                    )
                print(f"Already applied: {migration_path.name}")
                continue

            connection.execute(sql)
            connection.execute(
                "INSERT INTO app_schema_migrations (version, checksum) VALUES (%s, %s)",
                (migration_path.name, checksum),
            )
            print(f"Applied: {migration_path.name}")


if __name__ == "__main__":
    main()
