"""Shared mailbox MCP tool definitions."""

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient
from ...utils.timestamp import format_timestamp


_NOT_CONFIGURED = "Mailbox not configured. Set MAILBOX_URL and MAILBOX_API_KEY env vars."


def create_mailbox_tools(mcp: FastMCP, mailbox: MailboxClient | None) -> dict:
    """Register mailbox tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        mailbox: MailboxClient instance, or None if not configured

    Returns:
        Dict mapping tool names to their callable functions (for testing).

    Note:
        If mailbox is None, tools will be registered but will return
        a "not configured" message when called.
    """

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
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            result = await mailbox.send_message(recipients, body, subject, task_id=task_id)
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
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            messages = await mailbox.check_mailbox(unread_only, limit)
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
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            msg = await mailbox.read_message(message_id)
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
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            messages = await mailbox.browse_feed(
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
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            count = await mailbox.unread_count()
            if count == 0:
                return "No unread messages."
            return f"{count} unread message{'s' if count != 1 else ''}."
        except Exception as e:
            return f"Error checking unread count: {e}"

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
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            tasks = await mailbox.get_tasks(assignee=assignee, status=status, limit=limit)
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

    @mcp.tool()
    async def get_task(task_id: int) -> str:
        """Get full details of a specific task by ID.

        Args:
            task_id: The task ID to fetch.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            t = await mailbox.get_task(task_id)
            lines = [
                f"Task #{t['id']}",
                f"Status: {t['status']}",
                f"Subject: {t['subject'] or '(no subject)'}",
                f"Assignee: {t['assignee']}",
                f"Creator: {t['creator']}",
                f"Created: {format_timestamp(t['created_at'])}",
            ]
            if t.get("completed_at"):
                lines.append(f"Completed: {format_timestamp(t['completed_at'])}")
            if t.get("host"):
                lines.append(f"Host: {t['host']}")
            if t.get("session_name"):
                lines.append(f"Session: {t['session_name']}")
            if t.get("working_dir"):
                lines.append(f"Working dir: {t['working_dir']}")
            if t.get("output"):
                lines.append(f"\nOutput: {t['output']}")
            lines.append(f"\nPrompt:\n{t['prompt']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching task: {e}"

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
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            result = await mailbox.update_task(task_id, status=status, output=output)
            return (
                f"Task #{result['id']} updated.\n"
                f"  Status: {result['status']}\n"
                f"  Assignee: {result['assignee']}"
            )
        except Exception as e:
            return f"Error updating task: {e}"

    return {
        "send_message": send_message,
        "check_mailbox": check_mailbox,
        "read_message": read_message,
        "browse_feed": browse_feed,
        "unread_count": unread_count,
        "list_tasks": list_tasks,
        "get_task": get_task,
        "update_task": update_task,
    }
