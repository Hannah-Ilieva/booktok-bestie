from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).with_name("booktok.db")


def initialize_database():
    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                genre TEXT,
                status TEXT NOT NULL DEFAULT 'Want to Read',
                total_pages INTEGER,
                current_page INTEGER NOT NULL DEFAULT 0,
                rating REAL,
                review TEXT,
                mood TEXT,
                tropes TEXT,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()
    finally:
        connection.close()


def add_book(title, author, genre, status, total_pages):
    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute(
            """
            INSERT INTO books (title, author, genre, status, total_pages)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, author, genre, status, total_pages)
        )
        connection.commit()
    finally:
        connection.close()


def get_books():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT title, author, genre, status, total_pages, current_page
            FROM books
            ORDER BY added_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()