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
                paper_parsed_path TEXT,
                code_index_path TEXT,
                alignment_path TEXT,
                paper_vector_path TEXT,
                code_vector_path TEXT,
                paper_bm25_path TEXT,
                code_bm25_path TEXT
            );
            """
        )

        # Get existing columns to make migration idempotent
        existing_columns = set()
        cursor = conn.execute("PRAGMA table_info(projects)")
        for row in cursor.fetchall():
            existing_columns.add(row[1])  # column name is at index 1

        # Define all columns that should exist
        required_columns = [
            ("focus_points", "TEXT"),
            ("paper_hash", "TEXT"),
            ("repo_hash", "TEXT"),
            ("paper_parsed_path", "TEXT"),
            ("code_index_path", "TEXT"),
            ("alignment_path", "TEXT"),
            ("paper_vector_path", "TEXT"),
            ("code_vector_path", "TEXT"),
            ("paper_bm25_path", "TEXT"),
            ("code_bm25_path", "TEXT"),
        ]

        # Add missing columns safely
        for column_name, column_type in required_columns:
            if column_name not in existing_columns:
                try:
                    conn.execute(
                        f"ALTER TABLE projects ADD COLUMN {column_name} {column_type}"
                    )
                except sqlite3.OperationalError:
                    pass  # Column might exist or other issue, ignore safely

        conn.commit()
    finally:
        conn.close()
