"""SQLite database layer using aiosqlite."""

from __future__ import annotations

import aiosqlite

from .config import DB_PATH

SCHEMA = """\
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender      TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS message_recipients (
    message_id  INTEGER NOT NULL REFERENCES messages(id),
    recipient   TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    read_at     TEXT,
    PRIMARY KEY (message_id, recipient)
);

CREATE TABLE IF NOT EXISTS message_reads (
    message_id  INTEGER NOT NULL REFERENCES messages(id),
    brother     TEXT NOT NULL,
    read_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (message_id, brother)
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()


async def insert_message(
    sender: str, subject: str, body: str, recipients: list[str]
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO messages (sender, subject, body) VALUES (?, ?, ?)",
            (sender, subject, body),
        )
        message_id = cursor.lastrowid
        for recipient in recipients:
            await db.execute(
                "INSERT INTO message_recipients (message_id, recipient) VALUES (?, ?)",
                (message_id, recipient),
            )
        await db.commit()
        return message_id
    finally:
        await db.close()


async def get_messages(
    recipient: str, unread_only: bool = False, limit: int = 50
) -> list[dict]:
    db = await get_db()
    try:
        query = """
            SELECT m.id, m.sender, m.subject, m.body, m.created_at, mr.is_read
            FROM messages m
            JOIN message_recipients mr ON m.id = mr.message_id
            WHERE mr.recipient = ?
        """
        params: list = [recipient]
        if unread_only:
            query += " AND mr.is_read = 0"
        query += " ORDER BY m.created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_message(message_id: int, recipient: str) -> dict | None:
    db = await get_db()
    try:
        # Get the message with read status for this recipient
        cursor = await db.execute(
            """
            SELECT m.id, m.sender, m.subject, m.body, m.created_at, mr.is_read
            FROM messages m
            JOIN message_recipients mr ON m.id = mr.message_id
            WHERE m.id = ? AND mr.recipient = ?
            """,
            (message_id, recipient),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        msg = dict(row)

        # Get all recipients for this message
        cursor = await db.execute(
            "SELECT recipient FROM message_recipients WHERE message_id = ?",
            (message_id,),
        )
        recipient_rows = await cursor.fetchall()
        msg["recipients"] = [r["recipient"] for r in recipient_rows]

        # Get read_by info
        cursor = await db.execute(
            "SELECT brother, read_at FROM message_reads WHERE message_id = ?",
            (message_id,),
        )
        read_rows = await cursor.fetchall()
        msg["read_by"] = [{"brother": r["brother"], "read_at": r["read_at"]} for r in read_rows]

        return msg
    finally:
        await db.close()


async def get_message_any(message_id: int) -> dict | None:
    """Get a message by ID without recipient scoping (for feed/view)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, sender, subject, body, created_at FROM messages WHERE id = ?",
            (message_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        msg = dict(row)

        cursor = await db.execute(
            "SELECT recipient FROM message_recipients WHERE message_id = ?",
            (message_id,),
        )
        recipient_rows = await cursor.fetchall()
        msg["recipients"] = [r["recipient"] for r in recipient_rows]

        cursor = await db.execute(
            "SELECT brother, read_at FROM message_reads WHERE message_id = ?",
            (message_id,),
        )
        read_rows = await cursor.fetchall()
        msg["read_by"] = [{"brother": r["brother"], "read_at": r["read_at"]} for r in read_rows]

        return msg
    finally:
        await db.close()


async def mark_read(message_id: int, recipient: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            UPDATE message_recipients
            SET is_read = 1, read_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE message_id = ? AND recipient = ? AND is_read = 0
            """,
            (message_id, recipient),
        )
        if cursor.rowcount > 0:
            await db.execute(
                "INSERT OR IGNORE INTO message_reads (message_id, brother) VALUES (?, ?)",
                (message_id, recipient),
            )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_unread_count(recipient: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT COUNT(*) as cnt
            FROM message_recipients
            WHERE recipient = ? AND is_read = 0
            """,
            (recipient,),
        )
        row = await cursor.fetchone()
        return row["cnt"]
    finally:
        await db.close()


async def mark_unread(message_id: int, brother: str) -> bool:
    """Mark a message as unread for a brother. Returns True if anything changed."""
    db = await get_db()
    try:
        changed = False
        # Reset is_read in message_recipients if they are a recipient
        cursor = await db.execute(
            """
            UPDATE message_recipients
            SET is_read = 0, read_at = NULL
            WHERE message_id = ? AND recipient = ? AND is_read = 1
            """,
            (message_id, brother),
        )
        if cursor.rowcount > 0:
            changed = True
        # Remove from message_reads
        cursor = await db.execute(
            "DELETE FROM message_reads WHERE message_id = ? AND brother = ?",
            (message_id, brother),
        )
        if cursor.rowcount > 0:
            changed = True
        await db.commit()
        return changed
    finally:
        await db.close()


async def record_read(message_id: int, brother: str) -> None:
    """Record that a brother has read/viewed a message. Idempotent."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO message_reads (message_id, brother) VALUES (?, ?)",
            (message_id, brother),
        )
        await db.commit()
    finally:
        await db.close()


async def update_message(
    message_id: int,
    subject: str | None = None,
    body: str | None = None,
) -> dict | None:
    """Update message subject/body. Returns updated message dict or None if not found."""
    db = await get_db()
    try:
        updates = []
        params: list = []

        if subject is not None:
            updates.append("subject = ?")
            params.append(subject)
        if body is not None:
            updates.append("body = ?")
            params.append(body)

        if updates:
            params.append(message_id)
            query = f"UPDATE messages SET {', '.join(updates)} WHERE id = ?"
            await db.execute(query, params)
            await db.commit()

        return await get_message_any(message_id)
    finally:
        await db.close()


async def delete_message(message_id: int) -> bool:
    """Delete a message and its recipients/reads. Returns True if deleted."""
    db = await get_db()
    try:
        # Delete related rows first
        await db.execute(
            "DELETE FROM message_recipients WHERE message_id = ?", (message_id,)
        )
        await db.execute(
            "DELETE FROM message_reads WHERE message_id = ?", (message_id,)
        )
        cursor = await db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_feed(
    *,
    sender: str | None = None,
    recipient: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return all messages with optional filters, including recipients and read_by."""
    db = await get_db()
    try:
        where_clauses: list[str] = []
        params: list = []

        if sender:
            where_clauses.append("m.sender = ?")
            params.append(sender)

        if recipient:
            where_clauses.append(
                "m.id IN (SELECT message_id FROM message_recipients WHERE recipient = ?)"
            )
            params.append(recipient)

        if query:
            where_clauses.append("(m.subject LIKE ? OR m.body LIKE ?)")
            like_param = f"%{query}%"
            params.extend([like_param, like_param])

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT m.id, m.sender, m.subject, m.body, m.created_at
            FROM messages m
            {where_sql}
            ORDER BY m.created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        messages = [dict(row) for row in rows]

        # Bulk-fetch recipients and read_by for all messages
        if messages:
            msg_ids = [m["id"] for m in messages]
            placeholders = ",".join("?" * len(msg_ids))

            cursor = await db.execute(
                f"SELECT message_id, recipient FROM message_recipients WHERE message_id IN ({placeholders})",
                msg_ids,
            )
            recip_rows = await cursor.fetchall()
            recip_map: dict[int, list[str]] = {}
            for r in recip_rows:
                recip_map.setdefault(r["message_id"], []).append(r["recipient"])

            cursor = await db.execute(
                f"SELECT message_id, brother, read_at FROM message_reads WHERE message_id IN ({placeholders})",
                msg_ids,
            )
            read_rows = await cursor.fetchall()
            read_map: dict[int, list[dict]] = {}
            for r in read_rows:
                read_map.setdefault(r["message_id"], []).append(
                    {"brother": r["brother"], "read_at": r["read_at"]}
                )

            for msg in messages:
                msg["recipients"] = recip_map.get(msg["id"], [])
                msg["read_by"] = read_map.get(msg["id"], [])

        return messages
    finally:
        await db.close()
