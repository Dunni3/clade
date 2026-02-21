"""Conductor-specific MCP tool definitions for task delegation via Ember."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient
from ...worker.client import EmberClient


_NOT_CONFIGURED = "Conductor not configured. Ensure HEARTH_URL and HEARTH_API_KEY are set."


def create_conductor_tools(
    mcp: FastMCP,
    mailbox: MailboxClient | None,
    worker_registry: dict[str, dict],
    hearth_url: str | None = None,
    hearth_api_key: str | None = None,
    mailbox_name: str | None = None,
) -> dict:
    """Register conductor tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        mailbox: MailboxClient instance, or None if not configured
        worker_registry: Dict of worker names to config dicts with keys:
            ember_url, ember_api_key, working_dir (optional)
        hearth_url: Hearth URL to pass to spawned worker sessions
        hearth_api_key: Not passed to workers — workers use their own key
        mailbox_name: The conductor's own name (used as sender_name when delegating)

    Returns:
        Dict mapping tool names to their callable functions (for testing).
    """

    def _get_ember_client(brother: str) -> EmberClient | None:
        worker = worker_registry.get(brother)
        if not worker:
            return None
        url = worker.get("ember_url")
        key = worker.get("ember_api_key") or worker.get("api_key")
        if not url or not key:
            return None
        return EmberClient(url, key, verify_ssl=False)

    @mcp.tool()
    async def delegate_task(
        brother: str,
        prompt: str,
        subject: str = "",
        parent_task_id: int | None = None,
        working_dir: str | None = None,
        max_turns: int = 50,
        card_id: int | None = None,
    ) -> str:
        """Delegate a task to a worker brother via their Ember server.

        Creates a task in the Hearth, sends it to the worker's Ember, and
        updates the task status.

        Args:
            brother: Worker name (e.g. "oppy").
            prompt: The task prompt/instructions.
            subject: Short description of the task.
            parent_task_id: Optional parent task ID for task tree linking. If not provided, auto-reads from TRIGGER_TASK_ID env var.
            working_dir: Override the worker's default working directory.
            max_turns: Maximum Claude turns for the task.
            card_id: Optional kanban card ID to link this task to. Creates a formal link so the card tracks which tasks are working on it.
        """
        if mailbox is None:
            return _NOT_CONFIGURED

        if brother not in worker_registry:
            available = ", ".join(worker_registry.keys()) or "(none)"
            return f"Unknown worker '{brother}'. Available workers: {available}"

        worker = worker_registry[brother]
        ember = _get_ember_client(brother)
        if ember is None:
            return f"Worker '{brother}' has no Ember configured."

        # Auto-link parent from env if not explicitly provided
        if parent_task_id is None:
            trigger_id = os.environ.get("TRIGGER_TASK_ID", "")
            if trigger_id:
                try:
                    parent_task_id = int(trigger_id)
                except (ValueError, TypeError):
                    pass  # Invalid env value, ignore

        # Create task in Hearth
        try:
            task_result = await mailbox.create_task(
                assignee=brother,
                prompt=prompt,
                subject=subject,
                parent_task_id=parent_task_id,
            )
            task_id = task_result["id"]
        except Exception as e:
            return f"Error creating task in Hearth: {e}"

        # Link task to card if card_id provided
        if card_id is not None:
            try:
                await mailbox.add_card_link(card_id, "task", str(task_id))
            except Exception:
                pass  # Non-fatal: task still created, link just not established

        # Send to Ember.
        # Don't pass hearth_url — the Ember process already has the correct
        # HEARTH_URL for its network context. The conductor's own URL (often
        # localhost) is unreachable from remote workers.
        wd = working_dir or worker.get("working_dir")
        try:
            ember_result = await ember.execute_task(
                prompt=prompt,
                subject=subject,
                task_id=task_id,
                working_dir=wd,
                max_turns=max_turns,
                hearth_url=None,
                hearth_api_key=worker.get("hearth_api_key") or worker.get("api_key"),
                hearth_name=brother,
                sender_name=mailbox_name,
            )
        except Exception as e:
            # Mark task as failed
            try:
                await mailbox.update_task(task_id, status="failed", output=str(e))
            except Exception:
                pass
            return f"Task #{task_id} created but Ember delegation failed: {e}"

        # Update task status
        try:
            await mailbox.update_task(task_id, status="launched")
        except Exception:
            pass

        session = ember_result.get("session_name", "?")
        result_lines = [
            f"Task #{task_id} delegated to {brother}.",
            f"  Subject: {subject or '(none)'}",
            f"  Session: {session}",
            f"  Status: launched",
        ]
        if card_id is not None:
            result_lines.append(f"  Linked to card: #{card_id}")
        return "\n".join(result_lines)

    @mcp.tool()
    async def check_worker_health(brother: str | None = None) -> str:
        """Check the health of worker Ember servers.

        Args:
            brother: Specific worker to check. If not provided, checks all workers.
        """
        workers = (
            {brother: worker_registry[brother]}
            if brother and brother in worker_registry
            else worker_registry
        )

        if brother and brother not in worker_registry:
            return f"Unknown worker '{brother}'."

        if not workers:
            return "No workers configured."

        lines = []
        for name, _config in workers.items():
            ember = _get_ember_client(name)
            if ember is None:
                lines.append(f"{name}: No Ember configured")
                continue
            try:
                result = await ember.health()
                lines.append(
                    f"{name}: Healthy\n"
                    f"  Active tasks: {result.get('active_tasks', '?')}\n"
                    f"  Uptime: {result.get('uptime_seconds', '?')}s"
                )
            except Exception as e:
                lines.append(f"{name}: Unreachable ({e})")

        return "\n\n".join(lines)

    @mcp.tool()
    async def list_worker_tasks(brother: str | None = None) -> str:
        """List active tasks on worker Ember servers.

        Args:
            brother: Specific worker to check. If not provided, checks all workers.
        """
        workers = (
            {brother: worker_registry[brother]}
            if brother and brother in worker_registry
            else worker_registry
        )

        if brother and brother not in worker_registry:
            return f"Unknown worker '{brother}'."

        if not workers:
            return "No workers configured."

        lines = []
        for name, _config in workers.items():
            ember = _get_ember_client(name)
            if ember is None:
                lines.append(f"{name}: No Ember configured")
                continue
            try:
                result = await ember.active_tasks()
                # New multi-aspen format, with fallback for old Embers
                aspens = result.get("aspens")
                if aspens is None:
                    active = result.get("active_task")
                    aspens = [active] if active else []

                if aspens:
                    n = len(aspens)
                    lines.append(f"{name}: {n} active aspen{'s' if n != 1 else ''}")
                    for a in aspens:
                        lines.append(
                            f"  - Task ID: {a.get('task_id', 'N/A')}\n"
                            f"    Subject: {a.get('subject', '(none)')}\n"
                            f"    Session: {a.get('session_name', '?')}"
                        )
                else:
                    lines.append(f"{name}: Idle")
            except Exception as e:
                lines.append(f"{name}: Unreachable ({e})")

        return "\n\n".join(lines)

    return {
        "delegate_task": delegate_task,
        "check_worker_health": check_worker_health,
        "list_worker_tasks": list_worker_tasks,
    }
