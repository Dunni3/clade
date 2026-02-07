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
