"""Lightweight MCP server for remote brothers (Oppy/Jerry).

Only exposes mailbox tools — no terminal spawning (that's Doot's job).
Requires env vars: MAILBOX_URL, MAILBOX_API_KEY, MAILBOX_NAME.
"""

import os

from mcp.server.fastmcp import FastMCP

from mailbox_client import MailboxClient
from timestamp_utils import format_timestamp

mcp = FastMCP("brother-mailbox")

_mailbox_url = os.environ.get("MAILBOX_URL")
_mailbox_api_key = os.environ.get("MAILBOX_API_KEY")
_mailbox_name = os.environ.get("MAILBOX_NAME")

_mailbox: MailboxClient | None = None
if _mailbox_url and _mailbox_api_key:
    _verify_ssl = not _mailbox_url.startswith("https://")  # self-signed cert
    _mailbox = MailboxClient(_mailbox_url, _mailbox_api_key, verify_ssl=_verify_ssl)

_NOT_CONFIGURED = "Mailbox not configured. Set MAILBOX_URL and MAILBOX_API_KEY env vars."


@mcp.tool()
async def send_message(
    recipients: list[str],
    body: str,
    subject: str = "",
) -> str:
    """Send a message to one or more brothers.

    Args:
        recipients: List of brother names (e.g. ["doot", "jerry"]).
        body: The message body.
        subject: Optional subject line.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        result = await _mailbox.send_message(recipients, body, subject)
        names = ", ".join(recipients)
        return f"Message sent to {names} (id: {result['id']})"
    except Exception as e:
        return f"Error sending message: {e}"


@mcp.tool()
async def check_mailbox(unread_only: bool = True, limit: int = 20) -> str:
    """Check the mailbox for messages.

    Args:
        unread_only: If true, only show unread messages.
        limit: Maximum number of messages to return.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        messages = await _mailbox.check_mailbox(unread_only, limit)
        if not messages:
            return "No messages." if not unread_only else "No unread messages."
        lines = []
        for msg in messages:
            read_marker = "" if msg["is_read"] else " [NEW]"
            subj = msg["subject"] or "(no subject)"
            lines.append(
                f"#{msg['id']}{read_marker} from {msg['sender']}: {subj}\n"
                f"  {msg['body'][:100]}{'...' if len(msg['body']) > 100 else ''}\n"
                f"  ({format_timestamp(msg['created_at'])})"
            )
        return "\n\n".join(lines)
    except Exception as e:
        return f"Error checking mailbox: {e}"


@mcp.tool()
async def read_message(message_id: int) -> str:
    """Read a specific message by ID (also marks it as read).

    Args:
        message_id: The message ID to read.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        msg = await _mailbox.read_message(message_id)
        recipients = ", ".join(msg["recipients"])
        subj = msg["subject"] or "(no subject)"
        lines = [
            f"Message #{msg['id']}",
            f"From: {msg['sender']}",
            f"To: {recipients}",
            f"Subject: {subj}",
            f"Date: {format_timestamp(msg['created_at'])}",
        ]
        if msg.get("read_by"):
            names = ", ".join(r["brother"] for r in msg["read_by"])
            lines.append(f"Read by: {names}")
        lines.append(f"\n{msg['body']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading message: {e}"


@mcp.tool()
async def browse_feed(
    limit: int = 20,
    offset: int = 0,
    sender: str | None = None,
    recipient: str | None = None,
    query: str | None = None,
) -> str:
    """Browse the shared message feed. Shows all brother-to-brother messages.

    Args:
        limit: Maximum number of messages to return.
        offset: Number of messages to skip (for pagination).
        sender: Filter by sender name.
        recipient: Filter by recipient name.
        query: Search keyword in subject and body.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        messages = await _mailbox.browse_feed(
            sender=sender, recipient=recipient, query=query, limit=limit, offset=offset
        )
        if not messages:
            return "No messages in feed."
        lines = []
        for msg in messages:
            recipients = ", ".join(msg["recipients"])
            subj = msg["subject"] or "(no subject)"
            body_preview = msg["body"][:100] + ("..." if len(msg["body"]) > 100 else "")
            read_names = ", ".join(r["brother"] for r in msg.get("read_by", []))
            entry = (
                f"#{msg['id']} from {msg['sender']} to {recipients}: {subj}\n"
                f"  {body_preview}\n"
                f"  ({format_timestamp(msg['created_at'])})"
            )
            if read_names:
                entry += f"\n  Read by: {read_names}"
            lines.append(entry)
        return "\n\n".join(lines)
    except Exception as e:
        return f"Error browsing feed: {e}"


@mcp.tool()
async def unread_count() -> str:
    """Get the number of unread messages in the mailbox."""
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        count = await _mailbox.unread_count()
        if count == 0:
            return "No unread messages."
        return f"{count} unread message{'s' if count != 1 else ''}."
    except Exception as e:
        return f"Error checking unread count: {e}"


# ---------------------------------------------------------------------------
# Task tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def update_task(
    task_id: int,
    status: str | None = None,
    output: str | None = None,
) -> str:
    """Update a task's status and/or output summary.

    Use this to mark tasks as in_progress, completed, or failed.

    Args:
        task_id: The task ID to update.
        status: New status (e.g. "in_progress", "completed", "failed").
        output: Output summary describing what was done or what went wrong.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        result = await _mailbox.update_task(task_id, status=status, output=output)
        return (
            f"Task #{result['id']} updated.\n"
            f"  Status: {result['status']}\n"
            f"  Assignee: {result['assignee']}"
        )
    except Exception as e:
        return f"Error updating task: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
