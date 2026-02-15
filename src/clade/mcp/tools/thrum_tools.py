"""Thrum MCP tool definitions."""

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient
from ...utils.timestamp import format_timestamp


_NOT_CONFIGURED = "Mailbox not configured. Set HEARTH_URL and HEARTH_API_KEY env vars."


def create_thrum_tools(mcp: FastMCP, mailbox: MailboxClient | None) -> dict:
    """Register thrum tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        mailbox: MailboxClient instance, or None if not configured

    Returns:
        Dict mapping tool names to their callable functions (for testing).
    """

    @mcp.tool()
    async def create_thrum(
        title: str = "",
        goal: str = "",
        plan: str | None = None,
        priority: str = "normal",
    ) -> str:
        """Create a new thrum (multi-step workflow).

        Args:
            title: Short title for the thrum.
            goal: What this thrum should accomplish.
            plan: Optional initial plan (can be set later).
            priority: Priority level (low, normal, high, urgent).
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            result = await mailbox.create_thrum(
                title=title, goal=goal, plan=plan, priority=priority
            )
            return f"Thrum #{result['id']} created: {title or '(untitled)'}"
        except Exception as e:
            return f"Error creating thrum: {e}"

    @mcp.tool()
    async def list_thrums(
        status: str | None = None,
        creator: str | None = None,
        limit: int = 20,
    ) -> str:
        """List thrums (multi-step workflows).

        Args:
            status: Filter by status (pending, planning, active, paused, completed, failed).
            creator: Filter by creator name.
            limit: Maximum number of thrums to return.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            thrums = await mailbox.get_thrums(
                status=status, creator=creator, limit=limit
            )
            if not thrums:
                return "No thrums found."
            lines = []
            for t in thrums:
                line = (
                    f"#{t['id']} [{t['status']}] {t['title'] or '(untitled)'}\n"
                    f"  Goal: {t['goal'][:100] or '(none)'}{'...' if len(t.get('goal', '')) > 100 else ''}\n"
                    f"  Priority: {t['priority']} | Creator: {t['creator']}\n"
                    f"  Created: {format_timestamp(t['created_at'])}"
                )
                if t.get("completed_at"):
                    line += f"\n  Completed: {format_timestamp(t['completed_at'])}"
                lines.append(line)
            return "\n\n".join(lines)
        except Exception as e:
            return f"Error listing thrums: {e}"

    @mcp.tool()
    async def get_thrum(thrum_id: int) -> str:
        """Get full details of a thrum, including linked tasks.

        Args:
            thrum_id: The thrum ID to fetch.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            t = await mailbox.get_thrum(thrum_id)
            lines = [
                f"Thrum #{t['id']}",
                f"Title: {t['title'] or '(untitled)'}",
                f"Status: {t['status']}",
                f"Priority: {t['priority']}",
                f"Creator: {t['creator']}",
                f"Created: {format_timestamp(t['created_at'])}",
            ]
            if t.get("started_at"):
                lines.append(f"Started: {format_timestamp(t['started_at'])}")
            if t.get("completed_at"):
                lines.append(f"Completed: {format_timestamp(t['completed_at'])}")
            if t.get("goal"):
                lines.append(f"\nGoal: {t['goal']}")
            if t.get("plan"):
                lines.append(f"\nPlan:\n{t['plan']}")
            if t.get("output"):
                lines.append(f"\nOutput: {t['output']}")

            tasks = t.get("tasks", [])
            if tasks:
                lines.append(f"\nLinked Tasks ({len(tasks)}):")
                for task in tasks:
                    lines.append(
                        f"  #{task['id']} [{task['status']}] "
                        f"{task['subject'] or '(no subject)'} — {task['assignee']}"
                    )
            else:
                lines.append("\nNo linked tasks.")

            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching thrum: {e}"

    @mcp.tool()
    async def update_thrum(
        thrum_id: int,
        title: str | None = None,
        goal: str | None = None,
        plan: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        output: str | None = None,
    ) -> str:
        """Update a thrum's details.

        Args:
            thrum_id: The thrum ID to update.
            title: New title.
            goal: New goal.
            plan: New or updated plan.
            status: New status (pending, planning, active, paused, completed, failed).
            priority: New priority (low, normal, high, urgent).
            output: Output summary.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            result = await mailbox.update_thrum(
                thrum_id,
                title=title,
                goal=goal,
                plan=plan,
                status=status,
                priority=priority,
                output=output,
            )
            return (
                f"Thrum #{result['id']} updated.\n"
                f"  Status: {result['status']}\n"
                f"  Title: {result['title'] or '(untitled)'}"
            )
        except Exception as e:
            return f"Error updating thrum: {e}"

    return {
        "create_thrum": create_thrum,
        "list_thrums": list_thrums,
        "get_thrum": get_thrum,
        "update_thrum": update_thrum,
    }
