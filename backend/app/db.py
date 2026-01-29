import sqlite3

from .config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                paper_url TEXT NOT NULL,
                repo_url TEXT NOT NULL,
                focus_points TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                paper_hash TEXT,
                repo_hash TEXT,
                paper_parsed_path TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
