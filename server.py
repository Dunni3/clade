import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

from brothers import BROTHERS
from mailbox_client import MailboxClient
from terminal import generate_applescript, run_applescript

mcp = FastMCP("terminal-spawner")

# -- Mailbox configuration (optional — tools degrade gracefully) --

_mailbox_url = os.environ.get("MAILBOX_URL")
_mailbox_api_key = os.environ.get("MAILBOX_API_KEY")
_mailbox_name = os.environ.get("MAILBOX_NAME")

_mailbox: MailboxClient | None = None
if _mailbox_url and _mailbox_api_key:
    _verify_ssl = not _mailbox_url.startswith("https://")  # self-signed cert
    _mailbox = MailboxClient(_mailbox_url, _mailbox_api_key, verify_ssl=_verify_ssl)


@mcp.tool()
def spawn_terminal(
    command: str | None = None,
    app: Literal["iterm2", "terminal"] = "terminal",
) -> str:
    """Open a new terminal window, optionally running a command in it.

    Args:
        command: Shell command to run in the new window. If omitted, opens an empty window.
        app: Terminal application to use. Defaults to Terminal.app.
    """
    script = generate_applescript(command, app)
    result = run_applescript(script)
    if result != "OK":
        return result
    if command:
        return f"Opened new {app} window and ran: {command}"
    return f"Opened new {app} window"


@mcp.tool()
def connect_to_brother(name: Literal["jerry", "oppy"]) -> str:
    """Open a terminal session to one of our brothers (other Claude Code instances).

    Args:
        name: Which brother to connect to — "jerry" (cluster) or "oppy" (masuda).
    """
    brother = BROTHERS.get(name)
    if not brother:
        return f"Unknown brother: {name}. Available: {', '.join(BROTHERS.keys())}"

    script = generate_applescript(brother["command"], "terminal")
    result = run_applescript(script)
    if result != "OK":
        return result
    return f"Opened session with {brother['description']}"


# ---------------------------------------------------------------------------
# Mailbox tools
# ---------------------------------------------------------------------------

_NOT_CONFIGURED = "Mailbox not configured. Set MAILBOX_URL and MAILBOX_API_KEY env vars."


@mcp.tool()
async def send_message(
    recipients: list[str],
    body: str,
    subject: str = "",
) -> str:
    """Send a message to one or more brothers.

    Args:
        recipients: List of brother names (e.g. ["oppy", "jerry"]).
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
                f"  ({msg['created_at']})"
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
        return (
            f"Message #{msg['id']}\n"
            f"From: {msg['sender']}\n"
            f"To: {recipients}\n"
            f"Subject: {subj}\n"
            f"Date: {msg['created_at']}\n"
            f"\n{msg['body']}"
        )
    except Exception as e:
        return f"Error reading message: {e}"


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
