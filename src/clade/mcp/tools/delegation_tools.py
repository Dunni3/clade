"""Shared Ember delegation tools for personal and worker MCP servers."""

from __future__ import annotations

import logging
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient
from ...worker.client import EmberClient
from ...worker.resolver import EmberResolutionError, resolve_ember_url

logger = logging.getLogger(__name__)


_NOT_CONFIGURED = "Delegation not configured. Ensure HEARTH_URL and HEARTH_API_KEY are set."


def create_delegation_tools(
    mcp: FastMCP,
    mailbox: MailboxClient | None,
    brothers_registry: dict[str, dict] | None = None,
    registry_loader: Callable[[], dict[str, dict]] | None = None,
    mailbox_name: str | None = None,
    hearth_url: str | None = None,
) -> dict:
    """Register Ember delegation tool with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with.
        mailbox: MailboxClient instance, or None if not configured.
        brothers_registry: Static dict of brother configs (deprecated, use registry_loader).
        registry_loader: Callable that returns fresh registry on each call.
        mailbox_name: The caller's own name (used as sender_name when delegating).
        hearth_url: Hearth URL to pass to spawned worker sessions. If not set,
            the Ember's own HEARTH_URL env var is used (which may have SSL issues).

    Returns:
        Dict mapping tool names to their callable functions (for testing).
    """

    def _get_registry() -> dict[str, dict]:
        if registry_loader is not None:
            return registry_loader()
        return brothers_registry or {}

    async def _get_ember_client(brother: str) -> tuple[EmberClient | None, list[str]]:
        """Resolve ember URL (registry-first) and build an EmberClient.

        Returns:
            (EmberClient, warnings) on success, (None, warnings) on failure.
        """
        registry = _get_registry()
        config = registry.get(brother, {})
        config_url = config.get("ember_url")
        key = config.get("ember_api_key") or config.get("api_key")

        try:
            resolution = await resolve_ember_url(brother, mailbox, config_url)
        except EmberResolutionError:
            return None, []

        for w in resolution.warnings:
            logger.info("Ember resolution [%s]: %s", brother, w)

        if not key:
            return None, resolution.warnings

        return EmberClient(resolution.url, key, verify_ssl=False), resolution.warnings

    @mcp.tool()
    async def initiate_ember_task(
        brother: str,
        prompt: str,
        subject: str = "",
        parent_task_id: int | None = None,
        working_dir: str | None = None,
        max_turns: int | None = None,
        card_id: int | None = None,
        metadata: dict | None = None,
        on_complete: str | None = None,
        blocked_by_task_id: int | None = None,
        target_branch: str | None = None,
        project: str | None = None,
    ) -> str:
        """Delegate a task to a brother via their Ember server.

        Creates a task in the Hearth, sends it to the brother's Ember, and
        updates the task status. If blocked_by_task_id is set, the task is
        created but not delegated — it will be auto-delegated when the
        blocking task completes.

        Args:
            brother: Brother name (e.g. "oppy").
            prompt: The task prompt/instructions.
            subject: Short description of the task.
            parent_task_id: Optional parent task ID for task tree linking.
            working_dir: Override the brother's default working directory.
            max_turns: Optional maximum Claude turns. If not set, no turn limit is applied.
            card_id: Optional kanban card ID to link this task to.
            metadata: Optional dict stored on root tasks. Supports keys like "max_depth" to configure tree behavior.
            on_complete: Optional follow-up instructions for the Conductor when this task completes or fails.
            blocked_by_task_id: Optional task ID that must complete before this task runs. The task will stay in 'pending' until the blocking task completes, then auto-delegate.
            target_branch: Optional git branch to check out in the worktree. When set, the runner creates the worktree from this branch instead of HEAD.
            project: Optional project name (e.g. "clade", "omtra"). When set, working_dir is resolved from the brother's per-project mapping if no explicit working_dir is provided.
        """
        if mailbox is None:
            return _NOT_CONFIGURED

        registry = _get_registry()
        if brother not in registry:
            available = ", ".join(registry.keys()) or "(none)"
            return f"Unknown brother '{brother}'. Available brothers: {available}"

        config = registry[brother]
        ember, warnings = await _get_ember_client(brother)
        if ember is None:
            return f"Brother '{brother}' has no Ember configured."

        # Create task in Hearth
        try:
            task_result = await mailbox.create_task(
                assignee=brother,
                prompt=prompt,
                subject=subject,
                parent_task_id=parent_task_id,
                metadata=metadata,
                on_complete=on_complete,
                blocked_by_task_id=blocked_by_task_id,
                max_turns=max_turns,
                project=project,
            )
            task_id = task_result["id"]
        except Exception as e:
            return f"Error creating task in Hearth: {e}"

        # Link task to card if card_id provided
        if card_id is not None:
            try:
                await mailbox.add_card_link(card_id, "task", str(task_id))
            except Exception:
                pass  # Non-fatal

        # Check the *actual DB state* of blocked_by_task_id (not the input param).
        # insert_task auto-clears blocked_by when the blocker is already completed,
        # so the input param may say "blocked" while the DB says "ready to go".
        actual_blocked_by = task_result.get("blocked_by_task_id")
        if actual_blocked_by is not None:
            result_lines = [
                f"Task #{task_id} created (deferred — blocked by #{actual_blocked_by}).",
                f"  Subject: {subject or '(none)'}",
                f"  Assignee: {brother}",
                f"  Status: pending (waiting for #{actual_blocked_by} to complete)",
            ]
            if card_id is not None:
                result_lines.append(f"  Linked to card: #{card_id}")
            return "\n".join(result_lines)

        # Resolve working_dir: explicit override > project mapping > brother default
        wd = working_dir
        if wd is None and project:
            project_dirs = config.get("projects") or {}
            wd = project_dirs.get(project)
        if wd is None:
            wd = config.get("working_dir")
        try:
            ember_result = await ember.execute_task(
                prompt=prompt,
                subject=subject,
                task_id=task_id,
                working_dir=wd,
                max_turns=max_turns,
                hearth_url=config.get("hearth_url") or hearth_url,
                hearth_api_key=config.get("hearth_api_key") or config.get("ember_api_key") or config.get("api_key"),
                hearth_name=brother,
                sender_name=mailbox_name,
                target_branch=target_branch,
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
        if warnings:
            result_lines.append(f"  Note: {'; '.join(warnings)}")
        if card_id is not None:
            result_lines.append(f"  Linked to card: #{card_id}")
        return "\n".join(result_lines)

    return {
        "initiate_ember_task": initiate_ember_task,
    }
