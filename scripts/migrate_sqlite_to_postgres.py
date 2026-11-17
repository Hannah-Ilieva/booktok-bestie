from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from scripts.backup_sqlite import create_backup
from booktok.catalog import normalize_title
from booktok.db import connect


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = PROJECT_ROOT / "booktok.db"


def sqlite_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def migrate() -> tuple[Path, int, int]:
    if not SQLITE_PATH.is_file():
        raise SystemExit(f"SQLite shelf not found: {SQLITE_PATH}")

    backup_path = create_backup()
    source_uri = f"file:{SQLITE_PATH.as_posix()}?mode=ro"
    inserted = 0
    skipped = 0

    with closing(sqlite3.connect(source_uri, uri=True)) as sqlite_connection:
        sqlite_connection.row_factory = sqlite3.Row
        try:
            rows = sqlite_connection.execute(
                """
                SELECT id, title, author, genre, status, total_pages, current_page,
                       rating, review, mood, tropes, added_at
                FROM books ORDER BY id
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise SystemExit(f"Could not read the existing SQLite shelf: {exc}") from exc

    with connect() as postgres:
        for row in rows:
            exists = postgres.execute(
                "SELECT id FROM reading_shelf WHERE legacy_sqlite_id = %s",
                (row["id"],),
            ).fetchone()
            if exists:
                skipped += 1
                continue

            title = (row["title"] or "Untitled").strip()
            author = (row["author"] or "").strip()
            work = postgres.execute(
                """
                INSERT INTO works (title, normalized_title, authors)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (
                    title,
                    normalize_title(title),
                    author,
                ),
            ).fetchone()

            pages = row["total_pages"]
            if pages is not None and int(pages) <= 0:
                pages = None
            rating = row["rating"]
            if rating is not None:
                rating = min(max(float(rating), 0.0), 5.0)

            postgres.execute(
                """
                INSERT INTO reading_shelf
                    (work_id, legacy_sqlite_id, genre, status, total_pages,
                     current_page, rating, review, mood, tropes, added_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    work["id"],
                    row["id"],
                    row["genre"],
                    row["status"] or "Want to Read",
                    pages,
                    max(int(row["current_page"] or 0), 0),
                    rating,
                    row["review"],
                    row["mood"],
                    row["tropes"],
                    sqlite_timestamp(row["added_at"]),
                ),
            )
            inserted += 1

    return backup_path, inserted, skipped


def main() -> None:
    backup_path, inserted, skipped = migrate()
    print(f"SQLite backup created: {backup_path}")
    print(f"Imported {inserted} shelf row(s); {skipped} previously imported row(s) were left unchanged.")
    print("The SQLite database remains in place and was opened read-only.")
    print("Copy the backup outside the project before treating PostgreSQL as your only copy.")


if __name__ == "__main__":
    main()
