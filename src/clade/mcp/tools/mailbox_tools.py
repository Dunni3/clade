"""Shared mailbox MCP tool definitions."""

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient
from ...utils.timestamp import format_timestamp


_NOT_CONFIGURED = "Hearth not configured. Set HEARTH_URL and HEARTH_API_KEY env vars."


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
            if t.get("parent_task_id"):
                lines.append(f"Parent task: #{t['parent_task_id']}")
            if t.get("root_task_id"):
                lines.append(f"Root task: #{t['root_task_id']}")
            if t.get("host"):
                lines.append(f"Host: {t['host']}")
            if t.get("session_name"):
                lines.append(f"Session: {t['session_name']}")
            if t.get("working_dir"):
                lines.append(f"Working dir: {t['working_dir']}")
            children = t.get("children", [])
            if children:
                lines.append(f"\nChildren ({len(children)}):")
                for c in children:
                    lines.append(
                        f"  #{c['id']} [{c['status']}] {c.get('subject') or '(no subject)'}"
                        f" — {c['assignee']}"
                    )
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

    @mcp.tool()
    async def kill_task(task_id: int) -> str:
        """Kill a running task. Terminates the tmux session on the Ember and marks the task as killed.

        Args:
            task_id: The task ID to kill.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            result = await mailbox.kill_task(task_id)
            return (
                f"Task #{result['id']} killed.\n"
                f"  Status: {result['status']}\n"
                f"  Assignee: {result['assignee']}"
            )
        except Exception as e:
            return f"Error killing task: {e}"

    @mcp.tool()
    async def deposit_morsel(
        body: str,
        tags: list[str] | None = None,
        task_id: int | None = None,
        brother: str | None = None,
        card_id: int | None = None,
    ) -> str:
        """Deposit a morsel — a short note, observation, or log entry.

        Morsels are lightweight records that can be tagged and linked to tasks
        or brothers for later retrieval.

        Args:
            body: The morsel content.
            tags: Optional list of tags (e.g. ["conductor-tick", "debug"]).
            task_id: Optional task ID to link this morsel to.
            brother: Optional brother name to link this morsel to.
            card_id: Optional kanban card ID to link this morsel to.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            links = []
            if task_id is not None:
                links.append({"object_type": "task", "object_id": str(task_id)})
            if brother is not None:
                links.append({"object_type": "brother", "object_id": brother})
            if card_id is not None:
                links.append({"object_type": "card", "object_id": str(card_id)})
            result = await mailbox.create_morsel(
                body=body,
                tags=tags or None,
                links=links or None,
            )
            morsel_id = result.get("id", "?")
            return f"Morsel #{morsel_id} deposited."
        except Exception as e:
            return f"Error depositing morsel: {e}"

    @mcp.tool()
    async def list_morsels(
        creator: str | None = None,
        tag: str | None = None,
        task_id: int | None = None,
        card_id: int | None = None,
        limit: int = 20,
    ) -> str:
        """List morsels, optionally filtered by creator, tag, or linked object.

        Args:
            creator: Filter by creator name.
            tag: Filter by tag.
            task_id: Filter by linked task ID.
            card_id: Filter by linked kanban card ID.
            limit: Maximum number of morsels to return.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            object_type = None
            object_id = None
            if card_id is not None:
                object_type = "card"
                object_id = card_id
            elif task_id is not None:
                object_type = "task"
                object_id = task_id
            morsels = await mailbox.get_morsels(
                creator=creator,
                tag=tag,
                object_type=object_type,
                object_id=object_id,
                limit=limit,
            )
            if not morsels:
                return "No morsels found."
            lines = []
            for m in morsels:
                tags_str = ", ".join(m.get("tags", []))
                header = f"#{m['id']} by {m['creator']}"
                if tags_str:
                    header += f" [{tags_str}]"
                header += f" ({format_timestamp(m['created_at'])})"
                body_preview = m["body"][:120] + ("..." if len(m["body"]) > 120 else "")
                lines.append(f"{header}\n  {body_preview}")
            return "\n\n".join(lines)
        except Exception as e:
            return f"Error listing morsels: {e}"

    @mcp.tool()
    async def list_trees(limit: int = 20) -> str:
        """List task trees (hierarchies of parent-child tasks).

        Args:
            limit: Maximum number of trees to return.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            trees = await mailbox.get_trees(limit=limit)
            if not trees:
                return "No task trees found."
            lines = []
            for tree in trees:
                root = tree.get("root", tree)
                status_counts = tree.get("status_counts", {})
                counts_str = ", ".join(f"{k}: {v}" for k, v in status_counts.items())
                total = tree.get("total_tasks", "?")
                lines.append(
                    f"Tree #{root['id']}: {root.get('subject') or '(no subject)'}\n"
                    f"  Root assignee: {root['assignee']} | Tasks: {total}\n"
                    f"  Statuses: {counts_str or 'n/a'}"
                )
            return "\n\n".join(lines)
        except Exception as e:
            return f"Error listing trees: {e}"

    @mcp.tool()
    async def get_tree(root_task_id: int) -> str:
        """Get a task tree showing the full hierarchy from a root task.

        Args:
            root_task_id: The root task ID.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            tree = await mailbox.get_tree(root_task_id)
            lines = [f"Task tree rooted at #{root_task_id}:\n"]

            def _render_node(node: dict, depth: int = 0) -> None:
                indent = "  " * depth
                prefix = "└─ " if depth > 0 else ""
                subject = node.get("subject") or "(no subject)"
                lines.append(
                    f"{indent}{prefix}#{node['id']} [{node['status']}] {subject}"
                    f" — {node['assignee']}"
                )
                for child in node.get("children", []):
                    _render_node(child, depth + 1)

            root = tree.get("root", tree)
            _render_node(root)
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching tree: {e}"

    return {
        "send_message": send_message,
        "check_mailbox": check_mailbox,
        "read_message": read_message,
        "browse_feed": browse_feed,
        "unread_count": unread_count,
        "list_tasks": list_tasks,
        "get_task": get_task,
        "update_task": update_task,
        "kill_task": kill_task,
        "deposit_morsel": deposit_morsel,
        "list_morsels": list_morsels,
        "list_trees": list_trees,
        "get_tree": get_tree,
    }
