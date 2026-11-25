"""Ticket repository executing parameterized raw SQL queries."""

import sqlite3
from typing import Any, Dict, List, Optional


def save_ticket(
    conn: sqlite3.Connection,
    content: str,
    category: str,
    urgency: str,
    suggested_action: str,
    used_fallback: bool,
) -> Dict[str, Any]:
    """Persist a new ticket using parameterized SQL.

    Args:
        conn: Active sqlite3.Connection.
        content: Original raw text message.
        category: Classified category.
        urgency: Classified urgency level.
        suggested_action: Recommended next step.
        used_fallback: Flag indicating whether fallback heuristic was used.

    Returns:
        Dictionary representation of the saved ticket record.
    """
    query = """
        INSERT INTO tickets (content, category, urgency, suggested_action, used_fallback)
        VALUES (?, ?, ?, ?, ?)
    """
    cursor = conn.cursor()
    cursor.execute(
        query,
        (content, category, urgency, suggested_action, 1 if used_fallback else 0),
    )
    ticket_id = cursor.lastrowid

    select_query = """
        SELECT id, content, category, urgency, suggested_action, used_fallback, created_at
        FROM tickets
        WHERE id = ?
    """
    cursor.execute(select_query, (ticket_id,))
    row = cursor.fetchone()

    return {
        "id": row["id"],
        "content": row["content"],
        "category": row["category"],
        "urgency": row["urgency"],
        "suggested_action": row["suggested_action"],
        "used_fallback": bool(row["used_fallback"]),
        "created_at": str(row["created_at"]),
    }


def list_tickets(
    conn: sqlite3.Connection,
    urgency: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve tickets with optional urgency filter using parameterized SQL.

    Args:
        conn: Active sqlite3.Connection.
        urgency: Optional urgency filter value ('alta', 'media', 'baixa').

    Returns:
        List of ticket dictionaries ordered by id descending.
    """
    cursor = conn.cursor()

    if urgency:
        query = """
            SELECT id, content, category, urgency, suggested_action, used_fallback, created_at
            FROM tickets
            WHERE urgency = ?
            ORDER BY id DESC
        """
        cursor.execute(query, (urgency,))
    else:
        query = """
            SELECT id, content, category, urgency, suggested_action, used_fallback, created_at
            FROM tickets
            ORDER BY id DESC
        """
        cursor.execute(query)

    rows = cursor.fetchall()
    return [
        {
            "id": row["id"],
            "content": row["content"],
            "category": row["category"],
            "urgency": row["urgency"],
            "suggested_action": row["suggested_action"],
            "used_fallback": bool(row["used_fallback"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def get_ticket_metrics(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Compute aggregate ticket metrics using SQL COUNT and GROUP BY queries.

    Args:
        conn: Active sqlite3.Connection.

    Returns:
        Dictionary containing total tickets, category breakdown, urgency breakdown,
        and total fallback count.
    """
    cursor = conn.cursor()

    # Total tickets and fallback count
    cursor.execute("""
        SELECT
            COUNT(*) AS total_tickets,
            COALESCE(SUM(used_fallback), 0) AS fallback_count
        FROM tickets
    """)
    totals = cursor.fetchone()
    total_tickets = totals["total_tickets"] if totals else 0
    fallback_count = totals["fallback_count"] if totals else 0

    # Count by category
    cursor.execute("""
        SELECT category, COUNT(*) AS count
        FROM tickets
        GROUP BY category
    """)
    by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

    # Count by urgency
    cursor.execute("""
        SELECT urgency, COUNT(*) AS count
        FROM tickets
        GROUP BY urgency
    """)
    by_urgency = {row["urgency"]: row["count"] for row in cursor.fetchall()}

    return {
        "total_tickets": total_tickets,
        "by_category": by_category,
        "by_urgency": by_urgency,
        "fallback_count": fallback_count,
    }
