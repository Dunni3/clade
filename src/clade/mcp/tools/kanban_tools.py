"""Kanban board MCP tool definitions."""

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient

_NOT_CONFIGURED = "Hearth not configured. Set HEARTH_URL and HEARTH_API_KEY env vars."

COLUMNS = ("backlog", "todo", "in_progress", "done", "archived")
PRIORITIES = ("low", "normal", "high", "urgent")


def create_kanban_tools(mcp: FastMCP, mailbox: MailboxClient | None) -> dict:
    """Register kanban board tools with an MCP server."""

    @mcp.tool()
    async def create_card(
        title: str,
        description: str = "",
        col: str = "backlog",
        priority: str = "normal",
        assignee: str | None = None,
        labels: list[str] | None = None,
        links: list[dict] | None = None,
    ) -> str:
        """Create a kanban card.

        Args:
            title: Card title (required).
            description: Card description.
            col: Column — backlog, todo, in_progress, done, archived.
            priority: Priority — low, normal, high, urgent.
            assignee: Who is responsible for this card.
            labels: Optional labels/tags for categorization.
            links: Optional links to other objects. Each dict has `object_type` and `object_id` keys.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        if col not in COLUMNS:
            return f"Invalid column '{col}'. Must be one of: {', '.join(COLUMNS)}"
        if priority not in PRIORITIES:
            return f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"
        try:
            coerced_links = (
                [{"object_type": l["object_type"], "object_id": str(l["object_id"])} for l in links]
                if links
                else links
            )
            card = await mailbox.create_card(
                title=title,
                description=description,
                col=col,
                priority=priority,
                assignee=assignee,
                labels=labels,
                links=coerced_links,
            )
            return f"Card #{card['id']} created: {card['title']} [{card['col']}]"
        except Exception as e:
            return f"Error creating card: {e}"

    @mcp.tool()
    async def list_board(
        col: str | None = None,
        assignee: str | None = None,
        label: str | None = None,
        include_archived: bool = False,
    ) -> str:
        """Show kanban board cards, grouped by column.

        Args:
            col: Filter to a specific column.
            assignee: Filter by assignee.
            label: Filter by label.
            include_archived: Include archived cards (excluded by default).
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            cards = await mailbox.get_cards(
                col=col,
                assignee=assignee,
                label=label,
                include_archived=include_archived,
            )
            if not cards:
                return "No cards found."

            # Group by column
            by_col: dict[str, list[dict]] = {}
            for card in cards:
                by_col.setdefault(card["col"], []).append(card)

            lines = []
            display_order = [c for c in COLUMNS if c in by_col]
            for column in display_order:
                col_cards = by_col[column]
                lines.append(f"## {column.upper().replace('_', ' ')} ({len(col_cards)})")
                for c in col_cards:
                    priority_badge = f" [{c['priority']}]" if c["priority"] != "normal" else ""
                    assignee_badge = f" @{c['assignee']}" if c["assignee"] else ""
                    labels_str = f" ({', '.join(c.get('labels', []))})" if c.get("labels") else ""
                    lines.append(f"  #{c['id']}{priority_badge}{assignee_badge}: {c['title']}{labels_str}")
                lines.append("")

            return "\n".join(lines).rstrip()
        except Exception as e:
            return f"Error listing board: {e}"

    @mcp.tool()
    async def get_card(card_id: int) -> str:
        """Get full details of a kanban card.

        Args:
            card_id: The card ID.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            c = await mailbox.get_card(card_id)
            lines = [
                f"Card #{c['id']}: {c['title']}",
                f"Column: {c['col']}",
                f"Priority: {c['priority']}",
                f"Creator: {c['creator']}",
            ]
            if c.get("assignee"):
                lines.append(f"Assignee: {c['assignee']}")
            if c.get("labels"):
                lines.append(f"Labels: {', '.join(c['labels'])}")
            lines.append(f"Created: {c['created_at']}")
            lines.append(f"Updated: {c['updated_at']}")
            if c.get("links"):
                link_strs = [f"{l['object_type']} #{l['object_id']}" for l in c["links"]]
                lines.append(f"Links ({len(c['links'])}): {', '.join(link_strs)}")
            if c.get("description"):
                lines.append(f"\n{c['description']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching card: {e}"

    @mcp.tool()
    async def move_card(card_id: int, col: str) -> str:
        """Move a kanban card to a different column.

        Args:
            card_id: The card ID to move.
            col: Target column — backlog, todo, in_progress, done, archived.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        if col not in COLUMNS:
            return f"Invalid column '{col}'. Must be one of: {', '.join(COLUMNS)}"
        try:
            card = await mailbox.update_card(card_id, col=col)
            return f"Card #{card['id']} moved to {card['col']}."
        except Exception as e:
            return f"Error moving card: {e}"

    @mcp.tool()
    async def update_card(
        card_id: int,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        assignee: str | None = ...,  # type: ignore[assignment]
        labels: list[str] | None = ...,  # type: ignore[assignment]
        links: list[dict] | None = ...,  # type: ignore[assignment]
    ) -> str:
        """Update a kanban card's fields (use move_card to change column).

        Args:
            card_id: The card ID to update.
            title: New title.
            description: New description.
            priority: New priority — low, normal, high, urgent.
            assignee: New assignee (set to null to unassign).
            labels: New labels (replaces existing).
            links: New links (replaces existing). Each dict has `object_type` and `object_id` keys.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        if priority is not None and priority not in PRIORITIES:
            return f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"
        try:
            kwargs: dict = {}
            if title is not None:
                kwargs["title"] = title
            if description is not None:
                kwargs["description"] = description
            if priority is not None:
                kwargs["priority"] = priority
            if assignee is not ...:
                kwargs["assignee"] = assignee
            if labels is not ...:
                kwargs["labels"] = labels
            if links is not ...:
                kwargs["links"] = (
                    [{"object_type": l["object_type"], "object_id": str(l["object_id"])} for l in links]
                    if links
                    else links
                )
            card = await mailbox.update_card(card_id, **kwargs)
            return f"Card #{card['id']} updated: {card['title']} [{card['col']}]"
        except Exception as e:
            return f"Error updating card: {e}"

    @mcp.tool()
    async def archive_card(card_id: int) -> str:
        """Archive a kanban card (move to archived column).

        Args:
            card_id: The card ID to archive.
        """
        if mailbox is None:
            return _NOT_CONFIGURED
        try:
            card = await mailbox.archive_card(card_id)
            return f"Card #{card['id']} archived."
        except Exception as e:
            return f"Error archiving card: {e}"

    return {
        "create_card": create_card,
        "list_board": list_board,
        "get_card": get_card,
        "move_card": move_card,
        "update_card": update_card,
        "archive_card": archive_card,
    }
