import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

from brothers import BROTHERS
from mailbox_client import MailboxClient
from ssh_task import TaskResult, generate_session_name, initiate_task, wrap_prompt
from terminal import generate_applescript, run_applescript
from timestamp_utils import format_timestamp

mcp = FastMCP("terminal-spawner")

# -- Mailbox configuration (optional — tools degrade gracefully) --

_mailbox_url = os.environ.get("MAILBOX_URL")
_mailbox_api_key = os.environ.get("MAILBOX_API_KEY")
_mailbox_name = os.environ.get("MAILBOX_NAME")

_mailbox: MailboxClient | None = None
if _mailbox_url and _mailbox_api_key:
    _verify_ssl = not _mailbox_url.startswith("https://")  # self-signed cert
    _mailbox = MailboxClient(_mailbox_url, _mailbox_api_key, verify_ssl=_verify_ssl)


# DEPRECATED: prefer initiate_ssh_task for remote work. Kept for manual terminal use.
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


# DEPRECATED: prefer initiate_ssh_task for remote work. Kept for interactive sessions.
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
    task_id: int | None = None,
) -> str:
    """Send a message to one or more brothers.

    Args:
        recipients: List of brother names (e.g. ["oppy", "jerry"]).
        body: The message body.
        subject: Optional subject line.
        task_id: Optional task ID to link this message to.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        result = await _mailbox.send_message(recipients, body, subject, task_id=task_id)
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
async def initiate_ssh_task(
    brother: Literal["jerry", "oppy"],
    prompt: str,
    subject: str = "",
    working_dir: str | None = None,
    max_turns: int = 50,
    auto_pull: bool = False,
) -> str:
    """Send a task to a brother via SSH. Launches Claude Code in a detached tmux session.

    The brother will receive the prompt, do the work, and report back via the mailbox.
    Tasks are tracked in the mailbox database.

    WARNING: The remote Claude session runs with --dangerously-skip-permissions by default.
    This gives the brother full autonomous control — it can read/write/delete files and run
    arbitrary commands without human approval. Use max_turns to limit scope. Monitor live by
    attaching to the tmux session on the remote host if needed.

    Args:
        brother: Which brother to send the task to — "jerry" or "oppy".
        prompt: The task prompt / instructions for the brother.
        subject: Short description of the task.
        working_dir: Override the brother's default working directory.
        max_turns: Maximum Claude turns for the task (default 50). Lower for simple tasks.
        auto_pull: If true, git pull the MCP server repo on the remote host before launching. Default true.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED

    bro = BROTHERS.get(brother)
    if not bro:
        return f"Unknown brother: {brother}. Available: {', '.join(BROTHERS.keys())}"

    host = bro["host"]
    wd = working_dir or bro.get("working_dir")
    session_name = generate_session_name(brother, subject)

    # 1. Create task record in mailbox
    try:
        task_resp = await _mailbox.create_task(
            assignee=brother,
            prompt=prompt,
            subject=subject,
            session_name=session_name,
            host=host,
            working_dir=wd,
        )
        task_id = task_resp["id"]
    except Exception as e:
        return f"Error creating task record: {e}"

    # 2. Wrap prompt with task context
    sender = _mailbox_name or "doot"
    full_prompt = wrap_prompt(prompt, brother, subject, task_id, sender)

    # 3. Launch via SSH (pass mailbox credentials for hook-based task logging)
    result: TaskResult = initiate_task(
        host=host,
        working_dir=wd,
        prompt=full_prompt,
        session_name=session_name,
        max_turns=max_turns,
        auto_pull=auto_pull,
        task_id=task_id,
        mailbox_url=_mailbox_url,
        mailbox_api_key=_mailbox_api_key,
    )

    # 4. Update task status based on result
    if not result.success:
        try:
            await _mailbox.update_task(task_id, status="failed", output=result.message)
        except Exception:
            pass
        error_detail = result.message
        if result.stderr:
            error_detail += f"\nstderr: {result.stderr}"
        return f"Task #{task_id} failed to launch: {error_detail}"

    try:
        await _mailbox.update_task(task_id, status="launched")
    except Exception:
        pass

    return (
        f"Task #{task_id} launched successfully.\n"
        f"  Brother: {brother}\n"
        f"  Host: {host}\n"
        f"  Session: {session_name}\n"
        f"  Subject: {subject or '(none)'}\n"
        f"Brother {brother} will report back via the mailbox."
    )


@mcp.tool()
async def list_tasks(
    assignee: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List tasks from the mailbox task tracker.

    Args:
        assignee: Filter by assignee (e.g. "oppy", "jerry").
        status: Filter by status (e.g. "pending", "launched", "in_progress", "completed", "failed").
        limit: Maximum number of tasks to return.
    """
    if _mailbox is None:
        return _NOT_CONFIGURED
    try:
        tasks = await _mailbox.get_tasks(assignee=assignee, status=status, limit=limit)
        if not tasks:
            return "No tasks found."
        lines = []
        for t in tasks:
            line = (
                f"#{t['id']} [{t['status']}] {t['subject'] or '(no subject)'}\n"
                f"  Assignee: {t['assignee']} | Creator: {t['creator']}\n"
                f"  Created: {format_timestamp(t['created_at'])}"
            )
            if t.get("completed_at"):
                line += f"\n  Completed: {format_timestamp(t['completed_at'])}"
            lines.append(line)
        return "\n\n".join(lines)
    except Exception as e:
        return f"Error listing tasks: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
