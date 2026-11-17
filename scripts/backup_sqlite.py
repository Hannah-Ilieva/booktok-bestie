from datetime import datetime
from contextlib import closing
from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DB = PROJECT_ROOT / "booktok.db"
BACKUP_DIR = PROJECT_ROOT / "backups"


def create_backup() -> Path:
    if not SOURCE_DB.is_file():
        raise SystemExit(f"SQLite database not found: {SOURCE_DB}")

    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = BACKUP_DIR / f"booktok-{timestamp}.sqlite3"
    if backup_path.exists():
        raise SystemExit(f"Refusing to overwrite an existing backup: {backup_path}")

    source_uri = f"file:{SOURCE_DB.as_posix()}?mode=ro"
    try:
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            with closing(sqlite3.connect(backup_path)) as destination:
                source.backup(destination)
                result = destination.execute("PRAGMA integrity_check").fetchone()
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise

    if result != ("ok",):
        backup_path.unlink(missing_ok=True)
        raise SystemExit("The backup did not pass SQLite's integrity check.")

    return backup_path


def main() -> None:
    backup_path = create_backup()
    print(f"Created SQLite backup: {backup_path}")


if __name__ == "__main__":
    main()
