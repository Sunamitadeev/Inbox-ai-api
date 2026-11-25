"""Database connection manager and schema initialization."""

from contextlib import contextmanager
import os
import sqlite3
from typing import Generator

DATABASE_PATH = os.getenv("DATABASE_PATH", "inbox.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Create and configure a new SQLite database connection.

    Args:
        db_path: Optional explicit database file path.

    Returns:
        Configured sqlite3.Connection instance with row_factory set.
    """
    target_path = db_path or os.getenv("DATABASE_PATH", DATABASE_PATH)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db_connection(db_path: str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for managing SQLite transaction lifecycle.

    Yields:
        sqlite3.Connection: Active database connection.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | None = None) -> None:
    """Initialize database tables with the required schema.

    Args:
        db_path: Optional explicit database file path.
    """
    schema_sql = """
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        category TEXT NOT NULL,
        urgency TEXT NOT NULL,
        suggested_action TEXT NOT NULL,
        used_fallback INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_tickets_urgency ON tickets(urgency);
    CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
    """
    with get_db_connection(db_path) as conn:
        conn.executescript(schema_sql)
