"""SQLite database layer using aiosqlite."""

from __future__ import annotations

import json
import sqlite3

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

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    creator      TEXT NOT NULL,
    assignee     TEXT NOT NULL,
    subject      TEXT NOT NULL DEFAULT '',
    prompt       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    session_name TEXT,
    host         TEXT,
    working_dir  TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at   TEXT,
    completed_at TEXT,
    output       TEXT,
    metadata     TEXT,
    depth        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id),
    event_type TEXT NOT NULL,
    tool_name  TEXT,
    summary    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS api_keys (
    name       TEXT PRIMARY KEY,
    key        TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS morsels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    creator    TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS morsel_tags (
    morsel_id INTEGER NOT NULL REFERENCES morsels(id),
    tag       TEXT NOT NULL,
    PRIMARY KEY (morsel_id, tag)
);

CREATE TABLE IF NOT EXISTS morsel_links (
    morsel_id   INTEGER NOT NULL REFERENCES morsels(id),
    object_type TEXT NOT NULL,
    object_id   TEXT NOT NULL,
    PRIMARY KEY (morsel_id, object_type, object_id)
);

CREATE TABLE IF NOT EXISTS embers (
    name       TEXT PRIMARY KEY,
    ember_url  TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS brother_projects (
    brother_name TEXT NOT NULL,
    project      TEXT NOT NULL,
    working_dir  TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (brother_name, project)
);

CREATE TABLE IF NOT EXISTS task_parents (
    task_id    INTEGER NOT NULL REFERENCES tasks(id),
    parent_id  INTEGER NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (task_id, parent_id)
);

CREATE TABLE IF NOT EXISTS kanban_cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    col         TEXT NOT NULL DEFAULT 'backlog',
    priority    TEXT NOT NULL DEFAULT 'normal',
    assignee    TEXT,
    creator     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    project     TEXT
);

CREATE TABLE IF NOT EXISTS kanban_card_labels (
    card_id     INTEGER NOT NULL REFERENCES kanban_cards(id),
    label       TEXT NOT NULL,
    PRIMARY KEY (card_id, label)
);

CREATE TABLE IF NOT EXISTS kanban_card_links (
    card_id     INTEGER NOT NULL REFERENCES kanban_cards(id),
    object_type TEXT NOT NULL,
    object_id   TEXT NOT NULL,
    PRIMARY KEY (card_id, object_type, object_id)
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
        # Migration: add task_id to messages (idempotent — SQLite errors if column exists)
        try:
            await db.execute(
                "ALTER TABLE messages ADD COLUMN task_id INTEGER REFERENCES tasks(id)"
            )
        except Exception:
            pass  # Column already exists
        # Migration: add parent_task_id and root_task_id to tasks
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN parent_task_id INTEGER REFERENCES tasks(id)"
            )
        except Exception:
            pass
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN root_task_id INTEGER REFERENCES tasks(id)"
            )
        except Exception:
            pass
        # Migration: add metadata and depth columns to tasks
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN metadata TEXT"
            )
        except Exception:
            pass
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN depth INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass
        # Migration: add blocked_by_task_id to tasks (deferred task dependencies)
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN blocked_by_task_id INTEGER REFERENCES tasks(id)"
            )
        except Exception:
            pass
        # Migration: add max_turns to tasks (persisted for deferred task delegation)
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN max_turns INTEGER"
            )
        except Exception:
            pass
        # Migration: add project column to kanban_cards
        try:
            await db.execute(
                "ALTER TABLE kanban_cards ADD COLUMN project TEXT"
            )
            # Backfill: tag all existing cards as project='clade'
            await db.execute(
                "UPDATE kanban_cards SET project = 'clade' WHERE project IS NULL"
            )
        except Exception:
            pass
        # Migration: add on_complete column to tasks
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN on_complete TEXT"
            )
        except Exception:
            pass
        # Migration: add project column to tasks
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN project TEXT"
            )
        except Exception:
            pass

        # Migration: add status and last_seen columns to embers
        try:
            await db.execute(
                "ALTER TABLE embers ADD COLUMN status TEXT NOT NULL DEFAULT 'offline'"
            )
        except Exception:
            pass
        try:
            await db.execute(
                "ALTER TABLE embers ADD COLUMN last_seen TEXT"
            )
        except Exception:
            pass

        # -- FTS5 full-text search indexes (content-sync mode) --
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
                subject, prompt, output,
                content='tasks', content_rowid='id'
            )
        """)
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS morsels_fts USING fts5(
                body,
                content='morsels', content_rowid='id'
            )
        """)
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
                title, description,
                content='kanban_cards', content_rowid='id'
            )
        """)

        # FTS triggers: keep indexes in sync on INSERT/UPDATE/DELETE
        # Tasks
        await db.executescript("""
            CREATE TRIGGER IF NOT EXISTS tasks_fts_insert AFTER INSERT ON tasks BEGIN
                INSERT INTO tasks_fts(rowid, subject, prompt, output)
                VALUES (new.id, new.subject, new.prompt, COALESCE(new.output, ''));
            END;
            CREATE TRIGGER IF NOT EXISTS tasks_fts_delete BEFORE DELETE ON tasks BEGIN
                INSERT INTO tasks_fts(tasks_fts, rowid, subject, prompt, output)
                VALUES ('delete', old.id, old.subject, old.prompt, COALESCE(old.output, ''));
            END;
            CREATE TRIGGER IF NOT EXISTS tasks_fts_update AFTER UPDATE ON tasks BEGIN
                INSERT INTO tasks_fts(tasks_fts, rowid, subject, prompt, output)
                VALUES ('delete', old.id, old.subject, old.prompt, COALESCE(old.output, ''));
                INSERT INTO tasks_fts(rowid, subject, prompt, output)
                VALUES (new.id, new.subject, new.prompt, COALESCE(new.output, ''));
            END;
        """)
        # Morsels
        await db.executescript("""
            CREATE TRIGGER IF NOT EXISTS morsels_fts_insert AFTER INSERT ON morsels BEGIN
                INSERT INTO morsels_fts(rowid, body) VALUES (new.id, new.body);
            END;
            CREATE TRIGGER IF NOT EXISTS morsels_fts_delete BEFORE DELETE ON morsels BEGIN
                INSERT INTO morsels_fts(morsels_fts, rowid, body)
                VALUES ('delete', old.id, old.body);
            END;
            CREATE TRIGGER IF NOT EXISTS morsels_fts_update AFTER UPDATE ON morsels BEGIN
                INSERT INTO morsels_fts(morsels_fts, rowid, body)
                VALUES ('delete', old.id, old.body);
                INSERT INTO morsels_fts(rowid, body) VALUES (new.id, new.body);
            END;
        """)
        # Cards
        await db.executescript("""
            CREATE TRIGGER IF NOT EXISTS cards_fts_insert AFTER INSERT ON kanban_cards BEGIN
                INSERT INTO cards_fts(rowid, title, description)
                VALUES (new.id, new.title, COALESCE(new.description, ''));
            END;
            CREATE TRIGGER IF NOT EXISTS cards_fts_delete BEFORE DELETE ON kanban_cards BEGIN
                INSERT INTO cards_fts(cards_fts, rowid, title, description)
                VALUES ('delete', old.id, old.title, COALESCE(old.description, ''));
            END;
            CREATE TRIGGER IF NOT EXISTS cards_fts_update AFTER UPDATE ON kanban_cards BEGIN
                INSERT INTO cards_fts(cards_fts, rowid, title, description)
                VALUES ('delete', old.id, old.title, COALESCE(old.description, ''));
                INSERT INTO cards_fts(rowid, title, description)
                VALUES (new.id, new.title, COALESCE(new.description, ''));
            END;
        """)

        # Backfill FTS indexes for existing rows (idempotent — only if empty).
        # Must check the docsize shadow table, not the FTS table itself,
        # because SELECT COUNT(*) on a content-sync FTS table reads from
        # the source content table (always non-zero if data exists).
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM tasks_fts_docsize")
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            await db.execute("""
                INSERT INTO tasks_fts(rowid, subject, prompt, output)
                SELECT id, subject, prompt, COALESCE(output, '') FROM tasks
            """)
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM morsels_fts_docsize")
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            await db.execute("""
                INSERT INTO morsels_fts(rowid, body)
                SELECT id, body FROM morsels
            """)
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM cards_fts_docsize")
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            await db.execute("""
                INSERT INTO cards_fts(rowid, title, description)
                SELECT id, title, COALESCE(description, '') FROM kanban_cards
            """)

        await db.commit()
    finally:
        await db.close()


async def insert_message(
    sender: str,
    subject: str,
    body: str,
    recipients: list[str],
    task_id: int | None = None,
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO messages (sender, subject, body, task_id) VALUES (?, ?, ?, ?)",
            (sender, subject, body, task_id),
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
        # Also mark as read in message_recipients (used by inbox/unread count)
        await db.execute(
            """
            UPDATE message_recipients
            SET is_read = 1, read_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE message_id = ? AND recipient = ? AND is_read = 0
            """,
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


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


async def insert_task(
    creator: str,
    assignee: str,
    prompt: str,
    subject: str = "",
    session_name: str | None = None,
    host: str | None = None,
    working_dir: str | None = None,
    parent_task_id: int | None = None,
    parent_task_ids: list[int] | None = None,
    metadata: dict | None = None,
    on_complete: str | None = None,
    blocked_by_task_id: int | None = None,
    max_turns: int | None = None,
    project: str | None = None,
) -> int:
    db = await get_db()
    try:
        # Reconcile parent_task_id and parent_task_ids:
        # parent_task_ids takes precedence; parent_task_id is the primary (first).
        all_parent_ids: list[int] = []
        if parent_task_ids is not None and len(parent_task_ids) > 0:
            all_parent_ids = list(parent_task_ids)
            parent_task_id = all_parent_ids[0]
        elif parent_task_id is not None:
            all_parent_ids = [parent_task_id]

        root_task_id = None
        depth = 0

        if all_parent_ids:
            # Validate all parents exist, compute root and depth
            max_depth = 0
            root_ids_seen: set[int] = set()
            for pid in all_parent_ids:
                cursor = await db.execute(
                    "SELECT id, root_task_id, depth FROM tasks WHERE id = ?",
                    (pid,),
                )
                parent = await cursor.fetchone()
                if parent is None:
                    raise ValueError(f"Parent task {pid} does not exist")
                p_root = parent["root_task_id"] if parent["root_task_id"] is not None else parent["id"]
                root_ids_seen.add(p_root)
                p_depth = parent["depth"] or 0
                if p_depth > max_depth:
                    max_depth = p_depth

            if len(root_ids_seen) > 1:
                raise ValueError(
                    f"Cross-tree joins not supported: parents belong to different trees "
                    f"(roots: {sorted(root_ids_seen)})"
                )

            # root_task_id from primary parent
            cursor = await db.execute(
                "SELECT id, root_task_id FROM tasks WHERE id = ?",
                (parent_task_id,),
            )
            primary_parent = await cursor.fetchone()
            root_task_id = primary_parent["root_task_id"] if primary_parent["root_task_id"] is not None else primary_parent["id"]
            depth = max_depth + 1

        metadata_json = json.dumps(metadata) if metadata is not None else None

        # Validate blocking task exists (if specified).
        # Note: circular dependencies are structurally impossible because
        # blocked_by_task_id is only set at creation time and is immutable —
        # a new task cannot be the blocker of an already-existing task.
        if blocked_by_task_id is not None:
            cursor = await db.execute(
                "SELECT id, status FROM tasks WHERE id = ?",
                (blocked_by_task_id,),
            )
            blocker = await cursor.fetchone()
            if blocker is None:
                raise ValueError(f"Blocking task {blocked_by_task_id} does not exist")
            # If the blocking task is already completed, don't actually block
            if blocker["status"] == "completed":
                blocked_by_task_id = None

        # Auto-default parent_task_id to blocker when not explicitly set.
        # The simple sequential case ("do A then B") just works without
        # needing to set both. Explicit parent_task_id overrides this.
        if blocked_by_task_id is not None and parent_task_id is None:
            parent_task_id = blocked_by_task_id
            all_parent_ids = [parent_task_id]
            cursor = await db.execute(
                "SELECT id, root_task_id, depth FROM tasks WHERE id = ?",
                (parent_task_id,),
            )
            parent = await cursor.fetchone()
            # parent is guaranteed to exist (we already validated blocked_by_task_id above)
            root_task_id = parent["root_task_id"] if parent["root_task_id"] is not None else parent["id"]
            depth = (parent["depth"] or 0) + 1

        cursor = await db.execute(
            """INSERT INTO tasks (creator, assignee, subject, prompt, session_name, host, working_dir, parent_task_id, root_task_id, metadata, depth, on_complete, blocked_by_task_id, max_turns, project)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (creator, assignee, subject, prompt, session_name, host, working_dir, parent_task_id, root_task_id, metadata_json, depth, on_complete, blocked_by_task_id, max_turns, project),
        )
        task_id = cursor.lastrowid
        # Every task is a root of its own tree when it has no parent
        if root_task_id is None:
            await db.execute(
                "UPDATE tasks SET root_task_id = ? WHERE id = ?",
                (task_id, task_id),
            )

        # Insert into task_parents join table for all parents
        for pid in all_parent_ids:
            await db.execute(
                "INSERT INTO task_parents (task_id, parent_id) VALUES (?, ?)",
                (task_id, pid),
            )

        await db.commit()
        return task_id
    finally:
        await db.close()


async def get_tasks(
    *,
    assignee: str | None = None,
    status: str | None = None,
    creator: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = await get_db()
    try:
        where_clauses: list[str] = []
        params: list = []
        if assignee:
            where_clauses.append("assignee = ?")
            params.append(assignee)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if creator:
            where_clauses.append("creator = ?")
            params.append(creator)
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"""
            SELECT id, creator, assignee, subject, status, created_at, started_at, completed_at, parent_task_id, root_task_id, depth, blocked_by_task_id, project
            FROM tasks
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_task(task_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        task = dict(row)
        # Parse metadata JSON
        if task.get("metadata"):
            try:
                task["metadata"] = json.loads(task["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Get parent_task_ids from join table
        cursor = await db.execute(
            "SELECT parent_id FROM task_parents WHERE task_id = ? ORDER BY rowid",
            (task_id,),
        )
        parent_id_rows = await cursor.fetchall()
        task["parent_task_ids"] = [r["parent_id"] for r in parent_id_rows]

        # Get linked messages (explicit task_id OR mentions "task #N" / "task N")
        task_id_str = str(task_id)
        pattern_hash = f"%task #{task_id_str}%"
        pattern_space = f"%task {task_id_str}%"
        cursor = await db.execute(
            """SELECT DISTINCT m.id, m.sender, m.subject, m.body, m.created_at
               FROM messages m
               WHERE m.task_id = ?
                  OR m.subject LIKE ? OR m.body LIKE ?
                  OR m.subject LIKE ? OR m.body LIKE ?
               ORDER BY m.created_at ASC""",
            (task_id, pattern_hash, pattern_hash, pattern_space, pattern_space),
        )
        msg_rows = await cursor.fetchall()
        messages = [dict(r) for r in msg_rows]

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

        task["messages"] = messages

        # Get children
        cursor = await db.execute(
            """SELECT id, creator, assignee, subject, status, created_at, started_at, completed_at, parent_task_id, root_task_id, depth, blocked_by_task_id, project
               FROM tasks WHERE parent_task_id = ? ORDER BY created_at ASC""",
            (task_id,),
        )
        child_rows = await cursor.fetchall()
        task["children"] = [dict(r) for r in child_rows]

        # Get tasks blocked by this task
        cursor = await db.execute(
            """SELECT id, creator, assignee, subject, status, created_at, started_at, completed_at, parent_task_id, root_task_id, blocked_by_task_id, project
               FROM tasks WHERE blocked_by_task_id = ? ORDER BY created_at ASC""",
            (task_id,),
        )
        blocked_rows = await cursor.fetchall()
        task["blocked_tasks"] = [dict(r) for r in blocked_rows]

        # Get task events
        cursor = await db.execute(
            "SELECT id, task_id, event_type, tool_name, summary, created_at FROM task_events WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        )
        event_rows = await cursor.fetchall()
        task["events"] = [dict(r) for r in event_rows]

        # Get linked cards (reverse lookup: cards that link to this task)
        cursor = await db.execute(
            """SELECT c.id, c.title, c.col, c.priority
               FROM kanban_card_links cl
               JOIN kanban_cards c ON cl.card_id = c.id
               WHERE cl.object_type = 'task' AND cl.object_id = ?""",
            (task_id_str,),
        )
        card_rows = await cursor.fetchall()
        task["linked_cards"] = [dict(r) for r in card_rows]

        return task
    finally:
        await db.close()


async def insert_task_event(
    task_id: int,
    event_type: str,
    summary: str,
    tool_name: str | None = None,
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO task_events (task_id, event_type, tool_name, summary) VALUES (?, ?, ?, ?)",
            (task_id, event_type, tool_name, summary),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_task_events(task_id: int) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, task_id, event_type, tool_name, summary, created_at FROM task_events WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_task_parent_ids(task_id: int) -> list[int]:
    """Get all parent IDs for a task from the task_parents join table."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT parent_id FROM task_parents WHERE task_id = ? ORDER BY rowid",
            (task_id,),
        )
        rows = await cursor.fetchall()
        return [row["parent_id"] for row in rows]
    finally:
        await db.close()


async def get_tasks_blocked_by(task_id: int) -> list[dict]:
    """Get all pending tasks that are blocked by the given task."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, creator, assignee, subject, prompt, status, session_name, host,
                      working_dir, parent_task_id, root_task_id, blocked_by_task_id, max_turns, project, created_at
               FROM tasks
               WHERE blocked_by_task_id = ? AND status = 'pending'
               ORDER BY created_at ASC""",
            (task_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def clear_blocked_by(task_id: int) -> None:
    """Clear the blocked_by_task_id for a task (marks it as unblocked)."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET blocked_by_task_id = NULL WHERE id = ?",
            (task_id,),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


async def insert_api_key(name: str, key: str) -> bool:
    """Insert a new API key. Returns True on success, False if duplicate."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO api_keys (name, key) VALUES (?, ?)",
            (name, key),
        )
        await db.commit()
        return True
    except Exception:
        return False
    finally:
        await db.close()


async def get_api_key_by_key(key: str) -> str | None:
    """Look up a brother name by API key. Returns None if not found."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT name FROM api_keys WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["name"] if row else None
    finally:
        await db.close()


async def list_api_keys() -> list[dict]:
    """Return all registered key names and creation times (never the keys)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT name, created_at FROM api_keys ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_api_key_for_name(name: str) -> str | None:
    """Look up an API key by brother name. Returns the key string or None."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT key FROM api_keys WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        return row["key"] if row else None
    finally:
        await db.close()


async def get_all_member_names() -> set[str]:
    """Return the set of all registered member names from the api_keys table."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT name FROM api_keys")
        rows = await cursor.fetchall()
        return {row["name"] for row in rows}
    finally:
        await db.close()


async def delete_api_key(name: str) -> bool:
    """Remove an API key by name. Returns True if deleted."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM api_keys WHERE name = ?", (name,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_member_activity(extra_names: list[str] | None = None) -> list[dict]:
    """Get activity summary per member (DB api_keys + optional extra names)."""
    db = await get_db()
    try:
        # Get members from DB
        cursor = await db.execute("SELECT name FROM api_keys ORDER BY name")
        db_names = [row["name"] for row in await cursor.fetchall()]

        # Merge with env-var members (deduplicated, sorted)
        all_names = set(db_names)
        if extra_names:
            all_names.update(extra_names)
        members = sorted(all_names)

        result = []
        for name in members:
            # Message stats
            cursor = await db.execute(
                """SELECT COUNT(*) as cnt, MAX(created_at) as last_at
                   FROM messages WHERE sender = ?""",
                (name,),
            )
            msg_row = await cursor.fetchone()

            # Task stats (as creator or assignee)
            cursor = await db.execute(
                """SELECT
                     SUM(CASE WHEN status IN ('pending', 'launched', 'in_progress') THEN 1 ELSE 0 END) as active_tasks,
                     SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
                     SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
                     MAX(created_at) as last_at
                   FROM tasks WHERE creator = ? OR assignee = ?""",
                (name, name),
            )
            task_row = await cursor.fetchone()

            result.append({
                "name": name,
                "last_message_at": msg_row["last_at"],
                "messages_sent": msg_row["cnt"],
                "active_tasks": task_row["active_tasks"] or 0,
                "completed_tasks": task_row["completed_tasks"] or 0,
                "failed_tasks": task_row["failed_tasks"] or 0,
                "last_task_at": task_row["last_at"],
            })

        return result
    finally:
        await db.close()


async def update_task(
    task_id: int,
    *,
    status: str | None = None,
    output: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> dict | None:
    db = await get_db()
    try:
        updates: list[str] = []
        params: list = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if output is not None:
            updates.append("output = ?")
            params.append(output)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)

        if updates:
            params.append(task_id)
            query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
            cursor = await db.execute(query, params)
            if cursor.rowcount == 0:
                return None
            await db.commit()

        return await get_task(task_id)
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Task Trees
# ---------------------------------------------------------------------------


async def get_cards_for_objects(
    object_type: str, object_ids: list[str]
) -> dict[str, list[dict]]:
    """Reverse lookup: find cards linked to a set of objects.

    Returns a dict mapping object_id -> list of card summaries.
    """
    if not object_ids:
        return {}
    db = await get_db()
    try:
        placeholders = ",".join("?" * len(object_ids))
        cursor = await db.execute(
            f"""SELECT cl.object_id, c.id, c.title, c.col, c.priority
                FROM kanban_card_links cl
                JOIN kanban_cards c ON cl.card_id = c.id
                WHERE cl.object_type = ? AND cl.object_id IN ({placeholders})""",
            [object_type] + object_ids,
        )
        rows = await cursor.fetchall()
        result: dict[str, list[dict]] = {}
        for r in rows:
            oid = r["object_id"]
            result.setdefault(oid, []).append(
                {"id": r["id"], "title": r["title"], "col": r["col"], "priority": r["priority"]}
            )
        return result
    finally:
        await db.close()


async def count_children(task_id: int) -> int:
    """Count direct children of a task."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE parent_task_id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
        return row["cnt"]
    finally:
        await db.close()


async def update_task_parent(task_id: int, parent_task_id: int) -> None:
    """Reparent a task under a new parent.

    Validates parent exists, detects cycles, computes new root_task_id,
    and cascades root_task_id to all descendants.

    Raises ValueError on invalid parent or cycle.
    """
    db = await get_db()
    try:
        # Validate parent exists
        cursor = await db.execute(
            "SELECT id, root_task_id, depth FROM tasks WHERE id = ?",
            (parent_task_id,),
        )
        parent = await cursor.fetchone()
        if parent is None:
            raise ValueError(f"Parent task {parent_task_id} does not exist")

        # Validate task exists
        cursor = await db.execute(
            "SELECT id FROM tasks WHERE id = ?", (task_id,)
        )
        task = await cursor.fetchone()
        if task is None:
            raise ValueError(f"Task {task_id} does not exist")

        # Cycle detection: walk up from new parent, check if task_id appears
        cursor = await db.execute(
            """WITH RECURSIVE ancestors(id) AS (
                 SELECT ?
                 UNION ALL
                 SELECT t.parent_task_id FROM tasks t JOIN ancestors a ON t.id = a.id
                 WHERE t.parent_task_id IS NOT NULL
               )
               SELECT id FROM ancestors WHERE id = ?""",
            (parent_task_id, task_id),
        )
        if await cursor.fetchone() is not None:
            raise ValueError(
                f"Cannot reparent task {task_id} under {parent_task_id}: would create a cycle"
            )

        # Compute new root_task_id and depth
        new_root = parent["root_task_id"] if parent["root_task_id"] is not None else parent["id"]
        new_depth = (parent["depth"] or 0) + 1

        # Get old depth to compute delta for descendants
        cursor = await db.execute(
            "SELECT depth FROM tasks WHERE id = ?", (task_id,)
        )
        old_row = await cursor.fetchone()
        old_depth = old_row["depth"] or 0
        depth_delta = new_depth - old_depth

        # Update the task
        await db.execute(
            "UPDATE tasks SET parent_task_id = ?, root_task_id = ?, depth = ? WHERE id = ?",
            (parent_task_id, new_root, new_depth, task_id),
        )

        # Cascade root_task_id and adjust depth for all descendants
        await db.execute(
            """WITH RECURSIVE desc(id) AS (
                 SELECT id FROM tasks WHERE parent_task_id = ?
                 UNION ALL
                 SELECT t.id FROM tasks t JOIN desc d ON t.parent_task_id = d.id
               )
               UPDATE tasks SET root_task_id = ?, depth = depth + ? WHERE id IN (SELECT id FROM desc)""",
            (task_id, new_root, depth_delta),
        )

        await db.commit()
    finally:
        await db.close()


async def get_tree(root_task_id: int) -> dict | None:
    """Fetch a full task tree rooted at root_task_id."""
    db = await get_db()
    try:
        # Fetch root task
        cursor = await db.execute(
            "SELECT id, creator, assignee, subject, status, created_at, started_at, completed_at, parent_task_id, root_task_id, prompt, session_name, host, working_dir, output, metadata, depth, on_complete, blocked_by_task_id, project FROM tasks WHERE id = ?",
            (root_task_id,),
        )
        root_row = await cursor.fetchone()
        if root_row is None:
            return None
        root = dict(root_row)
        # Parse metadata JSON
        if root.get("metadata"):
            try:
                root["metadata"] = json.loads(root["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Fetch all descendants (exclude root itself)
        cursor = await db.execute(
            "SELECT id, creator, assignee, subject, status, created_at, started_at, completed_at, parent_task_id, root_task_id, prompt, session_name, host, working_dir, output, metadata, depth, on_complete, blocked_by_task_id, project FROM tasks WHERE root_task_id = ? AND id != ? ORDER BY created_at ASC",
            (root_task_id, root_task_id),
        )
        desc_rows = await cursor.fetchall()
        descendants = [dict(r) for r in desc_rows]
        for d in descendants:
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Build tree: index by ID, attach children
        nodes = {root["id"]: root}
        root["children"] = []
        for d in descendants:
            d["children"] = []
            nodes[d["id"]] = d

        for d in descendants:
            parent_id = d["parent_task_id"]
            if parent_id in nodes:
                nodes[parent_id]["children"].append(d)

        # Fetch all multi-parent edges for tasks in this tree
        all_node_ids = list(nodes.keys())
        placeholders = ",".join("?" * len(all_node_ids))
        cursor = await db.execute(
            f"SELECT task_id, parent_id FROM task_parents WHERE task_id IN ({placeholders}) ORDER BY rowid",
            all_node_ids,
        )
        tp_rows = await cursor.fetchall()

        # Build parent_task_ids for each node
        parent_ids_map: dict[int, list[int]] = {}
        for r in tp_rows:
            parent_ids_map.setdefault(r["task_id"], []).append(r["parent_id"])
        for tid, node in nodes.items():
            node["parent_task_ids"] = parent_ids_map.get(tid, [])

        # Fetch linked cards for all tasks in the tree
        all_task_ids = [str(tid) for tid in nodes.keys()]
        card_map = await get_cards_for_objects("task", all_task_ids)
        for tid, node in nodes.items():
            node["linked_cards"] = card_map.get(str(tid), [])

        return root
    finally:
        await db.close()


async def get_trees(limit: int = 50, offset: int = 0) -> list[dict]:
    """List task trees with aggregated stats."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT
                 d.root_task_id,
                 r.subject,
                 r.creator,
                 r.created_at,
                 COUNT(*) as total_tasks,
                 SUM(CASE WHEN d.status = 'completed' THEN 1 ELSE 0 END) as completed,
                 SUM(CASE WHEN d.status = 'failed' THEN 1 ELSE 0 END) as failed,
                 SUM(CASE WHEN d.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                 SUM(CASE WHEN d.status = 'pending' AND d.blocked_by_task_id IS NULL THEN 1 ELSE 0 END) as pending,
                 SUM(CASE WHEN d.status = 'killed' THEN 1 ELSE 0 END) as killed,
                 SUM(CASE WHEN d.status = 'pending' AND d.blocked_by_task_id IS NOT NULL THEN 1 ELSE 0 END) as blocked
               FROM tasks d
               JOIN tasks r ON d.root_task_id = r.id
               WHERE d.root_task_id IS NOT NULL
               GROUP BY d.root_task_id
               ORDER BY r.created_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Bidirectional link helpers
# ---------------------------------------------------------------------------


async def _create_reverse_links(
    db: aiosqlite.Connection,
    source_type: str,
    source_id: int,
    links: list[dict],
) -> None:
    """Create reverse links for bidirectional linking.

    Only cards and morsels have link tables, so reverse links are only created
    when those types are involved on both sides. Silently skips if the target
    object doesn't exist (foreign key constraint).
    """
    for link in links:
        target_type = link["object_type"]
        target_id = link["object_id"]

        try:
            if source_type == "card":
                if target_type == "morsel":
                    await db.execute(
                        "INSERT OR IGNORE INTO morsel_links (morsel_id, object_type, object_id) VALUES (?, 'card', ?)",
                        (int(target_id), str(source_id)),
                    )
                elif target_type == "card":
                    await db.execute(
                        "INSERT OR IGNORE INTO kanban_card_links (card_id, object_type, object_id) VALUES (?, 'card', ?)",
                        (int(target_id), str(source_id)),
                    )
            elif source_type == "morsel":
                if target_type == "card":
                    await db.execute(
                        "INSERT OR IGNORE INTO kanban_card_links (card_id, object_type, object_id) VALUES (?, 'morsel', ?)",
                        (int(target_id), str(source_id)),
                    )
                elif target_type == "morsel":
                    await db.execute(
                        "INSERT OR IGNORE INTO morsel_links (morsel_id, object_type, object_id) VALUES (?, 'morsel', ?)",
                        (int(target_id), str(source_id)),
                    )
        except (sqlite3.IntegrityError, ValueError):
            # Target doesn't exist or ID is not a valid integer — skip
            pass


async def _remove_reverse_links(
    db: aiosqlite.Connection,
    source_type: str,
    source_id: int,
    links: list[dict],
) -> None:
    """Remove reverse links when source links are being replaced."""
    for link in links:
        target_type = link["object_type"]
        target_id = link["object_id"]

        try:
            if source_type == "card":
                if target_type == "morsel":
                    await db.execute(
                        "DELETE FROM morsel_links WHERE morsel_id = ? AND object_type = 'card' AND object_id = ?",
                        (int(target_id), str(source_id)),
                    )
                elif target_type == "card":
                    await db.execute(
                        "DELETE FROM kanban_card_links WHERE card_id = ? AND object_type = 'card' AND object_id = ?",
                        (int(target_id), str(source_id)),
                    )
            elif source_type == "morsel":
                if target_type == "card":
                    await db.execute(
                        "DELETE FROM kanban_card_links WHERE card_id = ? AND object_type = 'morsel' AND object_id = ?",
                        (int(target_id), str(source_id)),
                    )
                elif target_type == "morsel":
                    await db.execute(
                        "DELETE FROM morsel_links WHERE morsel_id = ? AND object_type = 'morsel' AND object_id = ?",
                        (int(target_id), str(source_id)),
                    )
        except ValueError:
            # ID is not a valid integer — skip
            pass


# ---------------------------------------------------------------------------
# Morsels
# ---------------------------------------------------------------------------


async def insert_morsel(
    creator: str,
    body: str,
    tags: list[str] | None = None,
    links: list[dict] | None = None,
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO morsels (creator, body) VALUES (?, ?)",
            (creator, body),
        )
        morsel_id = cursor.lastrowid

        if tags:
            for tag in tags:
                await db.execute(
                    "INSERT INTO morsel_tags (morsel_id, tag) VALUES (?, ?)",
                    (morsel_id, tag),
                )

        if links:
            for link in links:
                await db.execute(
                    "INSERT INTO morsel_links (morsel_id, object_type, object_id) VALUES (?, ?, ?)",
                    (morsel_id, link["object_type"], link["object_id"]),
                )
            await _create_reverse_links(db, "morsel", morsel_id, links)

        await db.commit()
        return morsel_id
    finally:
        await db.close()


async def get_morsel(morsel_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, creator, body, created_at FROM morsels WHERE id = ?",
            (morsel_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        morsel = dict(row)

        cursor = await db.execute(
            "SELECT tag FROM morsel_tags WHERE morsel_id = ?",
            (morsel_id,),
        )
        morsel["tags"] = [r["tag"] for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT object_type, object_id FROM morsel_links WHERE morsel_id = ?",
            (morsel_id,),
        )
        morsel["links"] = [dict(r) for r in await cursor.fetchall()]

        return morsel
    finally:
        await db.close()


async def get_morsels(
    *,
    creator: str | None = None,
    tag: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    db = await get_db()
    try:
        where_clauses: list[str] = []
        params: list = []

        if creator:
            where_clauses.append("m.creator = ?")
            params.append(creator)
        if tag:
            where_clauses.append(
                "m.id IN (SELECT morsel_id FROM morsel_tags WHERE tag = ?)"
            )
            params.append(tag)
        if object_type and object_id:
            where_clauses.append(
                "m.id IN (SELECT morsel_id FROM morsel_links WHERE object_type = ? AND object_id = ?)"
            )
            params.extend([object_type, object_id])

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT m.id, m.creator, m.body, m.created_at
            FROM morsels m
            {where_sql}
            ORDER BY m.created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        morsels = [dict(row) for row in rows]

        # Bulk-fetch tags and links
        if morsels:
            morsel_ids = [m["id"] for m in morsels]
            placeholders = ",".join("?" * len(morsel_ids))

            cursor = await db.execute(
                f"SELECT morsel_id, tag FROM morsel_tags WHERE morsel_id IN ({placeholders})",
                morsel_ids,
            )
            tag_rows = await cursor.fetchall()
            tag_map: dict[int, list[str]] = {}
            for r in tag_rows:
                tag_map.setdefault(r["morsel_id"], []).append(r["tag"])

            cursor = await db.execute(
                f"SELECT morsel_id, object_type, object_id FROM morsel_links WHERE morsel_id IN ({placeholders})",
                morsel_ids,
            )
            link_rows = await cursor.fetchall()
            link_map: dict[int, list[dict]] = {}
            for r in link_rows:
                link_map.setdefault(r["morsel_id"], []).append(
                    {"object_type": r["object_type"], "object_id": r["object_id"]}
                )

            for morsel in morsels:
                morsel["tags"] = tag_map.get(morsel["id"], [])
                morsel["links"] = link_map.get(morsel["id"], [])

        return morsels
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Embers (registry)
# ---------------------------------------------------------------------------


async def upsert_ember(name: str, ember_url: str) -> dict:
    db = await get_db()
    try:
        now = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
        await db.execute(
            f"""INSERT INTO embers (name, ember_url, status, last_seen) VALUES (?, ?, 'online', {now})
               ON CONFLICT(name) DO UPDATE SET
                   ember_url = excluded.ember_url,
                   status = 'online',
                   last_seen = {now},
                   updated_at = {now}""",
            (name, ember_url),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT name, ember_url, status, last_seen, created_at, updated_at FROM embers WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        return dict(row)
    finally:
        await db.close()


async def get_embers() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT name, ember_url, status, last_seen, created_at, updated_at FROM embers ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def set_ember_offline(name: str) -> dict | None:
    db = await get_db()
    try:
        await db.execute(
            """UPDATE embers SET status = 'offline', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE name = ?""",
            (name,),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT name, ember_url, status, last_seen, created_at, updated_at FROM embers WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def delete_ember(name: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM embers WHERE name = ?", (name,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Brother Projects
# ---------------------------------------------------------------------------


async def upsert_brother_project(
    brother_name: str, project: str, working_dir: str
) -> dict:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO brother_projects (brother_name, project, working_dir)
               VALUES (?, ?, ?)
               ON CONFLICT(brother_name, project)
               DO UPDATE SET working_dir = excluded.working_dir,
                             updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')""",
            (brother_name, project, working_dir),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT brother_name, project, working_dir, updated_at FROM brother_projects WHERE brother_name = ? AND project = ?",
            (brother_name, project),
        )
        row = await cursor.fetchone()
        return dict(row)
    finally:
        await db.close()


async def get_brother_projects(brother_name: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT brother_name, project, working_dir, updated_at FROM brother_projects WHERE brother_name = ? ORDER BY project",
            (brother_name,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_brother_project(brother_name: str, project: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT brother_name, project, working_dir, updated_at FROM brother_projects WHERE brother_name = ? AND project = ?",
            (brother_name, project),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def delete_brother_project(brother_name: str, project: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM brother_projects WHERE brother_name = ? AND project = ?",
            (brother_name, project),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Kanban Cards
# ---------------------------------------------------------------------------

KANBAN_COLUMNS = {"backlog", "todo", "in_progress", "done", "archived"}
KANBAN_PRIORITIES = {"low", "normal", "high", "urgent"}
_PRIORITY_ORDER = {"urgent": 4, "high": 3, "normal": 2, "low": 1}


async def insert_card(
    creator: str,
    title: str,
    description: str = "",
    col: str = "backlog",
    priority: str = "normal",
    assignee: str | None = None,
    labels: list[str] | None = None,
    links: list[dict] | None = None,
    project: str | None = None,
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO kanban_cards (creator, title, description, col, priority, assignee, project) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (creator, title, description, col, priority, assignee, project),
        )
        card_id = cursor.lastrowid
        if labels:
            for label in labels:
                await db.execute(
                    "INSERT INTO kanban_card_labels (card_id, label) VALUES (?, ?)",
                    (card_id, label),
                )
        if links:
            for link in links:
                await db.execute(
                    "INSERT INTO kanban_card_links (card_id, object_type, object_id) VALUES (?, ?, ?)",
                    (card_id, link["object_type"], link["object_id"]),
                )
            await _create_reverse_links(db, "card", card_id, links)
        await db.commit()
        return card_id
    finally:
        await db.close()


async def get_card(card_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, title, description, col, priority, assignee, creator, created_at, updated_at, project FROM kanban_cards WHERE id = ?",
            (card_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        card = dict(row)
        cursor = await db.execute(
            "SELECT label FROM kanban_card_labels WHERE card_id = ?",
            (card_id,),
        )
        card["labels"] = [r["label"] for r in await cursor.fetchall()]
        cursor = await db.execute(
            "SELECT object_type, object_id FROM kanban_card_links WHERE card_id = ?",
            (card_id,),
        )
        card["links"] = [dict(r) for r in await cursor.fetchall()]
        return card
    finally:
        await db.close()


async def get_cards(
    *,
    col: str | None = None,
    assignee: str | None = None,
    creator: str | None = None,
    priority: str | None = None,
    label: str | None = None,
    project: str | None = None,
    include_archived: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    db = await get_db()
    try:
        where_clauses: list[str] = []
        params: list = []

        if col:
            where_clauses.append("c.col = ?")
            params.append(col)
        elif not include_archived:
            where_clauses.append("c.col != 'archived'")

        if assignee:
            where_clauses.append("c.assignee = ?")
            params.append(assignee)
        if creator:
            where_clauses.append("c.creator = ?")
            params.append(creator)
        if priority:
            where_clauses.append("c.priority = ?")
            params.append(priority)
        if label:
            where_clauses.append(
                "c.id IN (SELECT card_id FROM kanban_card_labels WHERE label = ?)"
            )
            params.append(label)
        if project:
            where_clauses.append("c.project = ?")
            params.append(project)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT c.id, c.title, c.description, c.col, c.priority, c.assignee, c.creator, c.created_at, c.updated_at, c.project
            FROM kanban_cards c
            {where_sql}
            ORDER BY
                CASE c.priority
                    WHEN 'urgent' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 1
                    ELSE 0
                END DESC,
                c.updated_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        cards = [dict(row) for row in rows]

        # Bulk-fetch labels and links
        if cards:
            card_ids = [c["id"] for c in cards]
            placeholders = ",".join("?" * len(card_ids))
            cursor = await db.execute(
                f"SELECT card_id, label FROM kanban_card_labels WHERE card_id IN ({placeholders})",
                card_ids,
            )
            label_rows = await cursor.fetchall()
            label_map: dict[int, list[str]] = {}
            for r in label_rows:
                label_map.setdefault(r["card_id"], []).append(r["label"])

            cursor = await db.execute(
                f"SELECT card_id, object_type, object_id FROM kanban_card_links WHERE card_id IN ({placeholders})",
                card_ids,
            )
            link_rows = await cursor.fetchall()
            link_map: dict[int, list[dict]] = {}
            for r in link_rows:
                link_map.setdefault(r["card_id"], []).append(
                    {"object_type": r["object_type"], "object_id": r["object_id"]}
                )

            for card in cards:
                card["labels"] = label_map.get(card["id"], [])
                card["links"] = link_map.get(card["id"], [])

        return cards
    finally:
        await db.close()


async def update_card(card_id: int, **kwargs) -> dict | None:
    """Update a card. Pass only the fields to change.

    Supported kwargs: title, description, col, priority, assignee, labels, project.
    """
    db = await get_db()
    try:
        updates: list[str] = []
        params: list = []

        for field in ("title", "description", "col", "priority", "assignee", "project"):
            if field in kwargs:
                updates.append(f"{field} = ?")
                params.append(kwargs[field])

        if updates:
            updates.append("updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")
            params.append(card_id)
            query = f"UPDATE kanban_cards SET {', '.join(updates)} WHERE id = ?"
            cursor = await db.execute(query, params)
            if cursor.rowcount == 0:
                return None

        if "labels" in kwargs:
            # Replace labels
            await db.execute("DELETE FROM kanban_card_labels WHERE card_id = ?", (card_id,))
            labels = kwargs["labels"]
            if labels:
                for lbl in labels:
                    await db.execute(
                        "INSERT INTO kanban_card_labels (card_id, label) VALUES (?, ?)",
                        (card_id, lbl),
                    )

        if "links" in kwargs:
            # Fetch old links to remove their reverse links
            cursor = await db.execute(
                "SELECT object_type, object_id FROM kanban_card_links WHERE card_id = ?",
                (card_id,),
            )
            old_links = [dict(r) for r in await cursor.fetchall()]
            if old_links:
                await _remove_reverse_links(db, "card", card_id, old_links)

            # Replace links
            await db.execute("DELETE FROM kanban_card_links WHERE card_id = ?", (card_id,))
            links = kwargs["links"]
            if links:
                for link in links:
                    await db.execute(
                        "INSERT INTO kanban_card_links (card_id, object_type, object_id) VALUES (?, ?, ?)",
                        (card_id, link["object_type"], link["object_id"]),
                    )
                await _create_reverse_links(db, "card", card_id, links)

        await db.commit()
        return await get_card(card_id)
    finally:
        await db.close()


async def delete_card(card_id: int) -> bool:
    db = await get_db()
    try:
        # Remove reverse links for this card's outgoing links
        cursor = await db.execute(
            "SELECT object_type, object_id FROM kanban_card_links WHERE card_id = ?",
            (card_id,),
        )
        old_links = [dict(r) for r in await cursor.fetchall()]
        if old_links:
            await _remove_reverse_links(db, "card", card_id, old_links)

        await db.execute("DELETE FROM kanban_card_links WHERE card_id = ?", (card_id,))
        await db.execute("DELETE FROM kanban_card_labels WHERE card_id = ?", (card_id,))
        cursor = await db.execute("DELETE FROM kanban_cards WHERE id = ?", (card_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------

VALID_SEARCH_TYPES = {"task", "morsel", "card"}


async def search(
    query: str,
    entity_types: list[str] | None = None,
    limit: int = 20,
    created_after: str | None = None,
    created_before: str | None = None,
) -> list[dict]:
    """Search across tasks, morsels, and cards using FTS5.

    Returns a merged, rank-sorted list of results.
    """
    types = set(entity_types) if entity_types else VALID_SEARCH_TYPES
    results: list[dict] = []

    db = await get_db()
    try:
        if "task" in types:
            date_clauses = ""
            date_params: list = []
            if created_after:
                date_clauses += " AND t.created_at >= ?"
                date_params.append(created_after)
            if created_before:
                date_clauses += " AND t.created_at <= ?"
                date_params.append(created_before)
            cursor = await db.execute(
                f"""
                SELECT
                    t.id, t.subject, t.status, t.assignee, t.creator, t.created_at,
                    snippet(tasks_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet_subject,
                    snippet(tasks_fts, 1, '<mark>', '</mark>', '...', 32) AS snippet_prompt,
                    snippet(tasks_fts, 2, '<mark>', '</mark>', '...', 32) AS snippet_output,
                    tasks_fts.rank
                FROM tasks_fts
                JOIN tasks t ON t.id = tasks_fts.rowid
                WHERE tasks_fts MATCH ?{date_clauses}
                ORDER BY tasks_fts.rank
                LIMIT ?
                """,
                (query, *date_params, limit),
            )
            for row in await cursor.fetchall():
                r = dict(row)
                # Pick best snippet (prefer subject, then prompt, then output)
                snippet = r["snippet_subject"]
                if not snippet or snippet == "...":
                    snippet = r["snippet_prompt"]
                if not snippet or snippet == "...":
                    snippet = r["snippet_output"] or ""
                results.append({
                    "type": "task",
                    "id": r["id"],
                    "title": r["subject"] or "(no subject)",
                    "snippet": snippet,
                    "rank": r["rank"],
                    "status": r["status"],
                    "assignee": r["assignee"],
                    "creator": r["creator"],
                    "created_at": r["created_at"],
                })

        if "morsel" in types:
            morsel_date_clauses = ""
            morsel_date_params: list = []
            if created_after:
                morsel_date_clauses += " AND m.created_at >= ?"
                morsel_date_params.append(created_after)
            if created_before:
                morsel_date_clauses += " AND m.created_at <= ?"
                morsel_date_params.append(created_before)
            cursor = await db.execute(
                f"""
                SELECT
                    m.id, m.creator, m.created_at,
                    snippet(morsels_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet,
                    morsels_fts.rank
                FROM morsels_fts
                JOIN morsels m ON m.id = morsels_fts.rowid
                WHERE morsels_fts MATCH ?{morsel_date_clauses}
                ORDER BY morsels_fts.rank
                LIMIT ?
                """,
                (query, *morsel_date_params, limit),
            )
            for row in await cursor.fetchall():
                r = dict(row)
                # Use first line of body as title
                body_line = r["snippet"].split("\n")[0][:80] if r["snippet"] else ""
                results.append({
                    "type": "morsel",
                    "id": r["id"],
                    "title": body_line,
                    "snippet": r["snippet"],
                    "rank": r["rank"],
                    "creator": r["creator"],
                    "created_at": r["created_at"],
                })

        if "card" in types:
            card_date_clauses = ""
            card_date_params: list = []
            if created_after:
                card_date_clauses += " AND c.created_at >= ?"
                card_date_params.append(created_after)
            if created_before:
                card_date_clauses += " AND c.created_at <= ?"
                card_date_params.append(created_before)
            cursor = await db.execute(
                f"""
                SELECT
                    c.id, c.title, c.col, c.priority, c.assignee, c.creator, c.created_at,
                    snippet(cards_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet_title,
                    snippet(cards_fts, 1, '<mark>', '</mark>', '...', 32) AS snippet_desc,
                    cards_fts.rank
                FROM cards_fts
                JOIN kanban_cards c ON c.id = cards_fts.rowid
                WHERE cards_fts MATCH ?{card_date_clauses}
                ORDER BY cards_fts.rank
                LIMIT ?
                """,
                (query, *card_date_params, limit),
            )
            for row in await cursor.fetchall():
                r = dict(row)
                snippet = r["snippet_title"]
                if not snippet or snippet == "...":
                    snippet = r["snippet_desc"] or ""
                results.append({
                    "type": "card",
                    "id": r["id"],
                    "title": r["title"],
                    "snippet": snippet,
                    "rank": r["rank"],
                    "col": r["col"],
                    "priority": r["priority"],
                    "assignee": r["assignee"],
                    "creator": r["creator"],
                    "created_at": r["created_at"],
                })

        # Sort by rank (lower = better in FTS5) and truncate
        results.sort(key=lambda x: x["rank"])
        return results[:limit]
    finally:
        await db.close()
