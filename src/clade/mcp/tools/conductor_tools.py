"""Conductor-specific MCP tool definitions for task delegation via Ember."""

from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient
from ...worker.client import EmberClient
from ...worker.resolver import EmberResolutionError, resolve_ember_url

logger = logging.getLogger(__name__)


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

    async def _get_ember_client(brother: str) -> tuple[EmberClient | None, list[str]]:
        """Resolve ember URL (registry-first) and build an EmberClient.

        Returns:
            (EmberClient, warnings) on success, (None, warnings) on failure.
        """
        worker = worker_registry.get(brother, {})
        config_url = worker.get("ember_url")
        key = worker.get("ember_api_key") or worker.get("api_key")

        try:
            resolution = await resolve_ember_url(brother, mailbox, config_url)
        except EmberResolutionError as exc:
            logger.warning("Ember resolution failed for %s: %s", brother, exc)
            return None, []

        for w in resolution.warnings:
            logger.info("Ember resolution [%s]: %s", brother, w)

        if not key:
            return None, resolution.warnings

        return EmberClient(resolution.url, key, verify_ssl=False), resolution.warnings

    async def _delegate_to_ember(
        brother: str,
        prompt: str,
        subject: str,
        task_id: int,
        working_dir: str | None,
        max_turns: int | None,
        target_branch: str | None,
        card_id: int | None,
        project: str | None,
    ) -> str:
        """Shared delegation logic: resolve working_dir, send to Ember, handle errors."""
        worker = worker_registry[brother]
        ember, warnings = await _get_ember_client(brother)
        if ember is None:
            return f"Worker '{brother}' has no Ember configured."

        # Resolve working_dir: explicit override > project mapping > worker default
        wd = working_dir
        if wd is None and project:
            project_dirs = worker.get("projects") or {}
            wd = project_dirs.get(project)
        if wd is None:
            wd = worker.get("working_dir")
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
                target_branch=target_branch,
            )
        except Exception as e:
            # Mark task as failed so it doesn't get orphaned in pending
            try:
                await mailbox.update_task(task_id, status="failed", output=f"Ember delegation failed: {e}")
            except Exception as status_err:
                logger.error(
                    "Task #%d orphaned in pending: Ember failed (%s) AND status update failed (%s)",
                    task_id, e, status_err,
                )
                return (
                    f"Task #{task_id} created but Ember delegation failed: {e}\n"
                    f"WARNING: Failed to mark task as failed ({status_err}) — task is orphaned in pending status."
                )
            return f"Task #{task_id} created but Ember delegation failed: {e}"

        # Update task status
        try:
            await mailbox.update_task(task_id, status="launched")
        except Exception as e:
            logger.error("Task #%d may be orphaned: launched on Ember but status update failed: %s", task_id, e)

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

    @mcp.tool()
    async def delegate_task(
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
        """Delegate a new root or explicitly-parented task to a worker brother.

        Use this for new initiatives, card implementations, or when you want to
        explicitly set the parent. For follow-up tasks after completion/failure,
        use delegate_child_task instead — it auto-inherits context and enforces
        depth limits.

        NOTE: This tool does NOT auto-link from TRIGGER_TASK_ID. Use
        delegate_child_task for automatic parent linking from the trigger context.

        Args:
            brother: Worker name (e.g. "oppy").
            prompt: The task prompt/instructions.
            subject: Short description of the task.
            parent_task_id: Optional parent task ID for task tree linking.
            working_dir: Override the worker's default working directory.
            max_turns: Optional maximum Claude turns. If not set, no turn limit is applied.
            card_id: Optional kanban card ID to link this task to. Creates a formal link so the card tracks which tasks are working on it.
            metadata: Optional dict stored on root tasks. Supports keys like "max_depth" to configure tree behavior.
            on_complete: Optional follow-up instructions for the Conductor when this task completes or fails.
            blocked_by_task_id: Optional task ID that must complete before this task runs. The task will stay in 'pending' until the blocking task completes, then auto-delegate.
            target_branch: Optional git branch to check out in the worktree. When set, the runner creates the worktree from this branch instead of HEAD.
            project: Optional project name (e.g. "clade", "omtra"). When set, working_dir is resolved from the brother's per-project mapping if no explicit working_dir is provided.
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

        # Resolve working_dir early so it's persisted on the task record.
        # Resolution order: explicit override > project mapping > worker default
        wd = working_dir
        if wd is None and project:
            project_dirs = worker.get("projects") or {}
            wd = project_dirs.get(project)
        if wd is None:
            wd = worker.get("working_dir")

        # Create task in Hearth
        try:
            task_result = await mailbox.create_task(
                assignee=brother,
                prompt=prompt,
                subject=subject,
                parent_task_id=parent_task_id,
                working_dir=wd,
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
                pass  # Non-fatal: task still created, link just not established

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

        return await _delegate_to_ember(
            brother=brother,
            prompt=prompt,
            subject=subject,
            task_id=task_id,
            working_dir=working_dir,
            max_turns=max_turns,
            target_branch=target_branch,
            card_id=card_id,
            project=project,
        )

    @mcp.tool()
    async def delegate_child_task(
        brother: str,
        prompt: str,
        subject: str = "",
        parent_task_ids: list[int] | None = None,
        working_dir: str | None = None,
        max_turns: int | None = None,
        card_id: int | None = None,
        on_complete: str | None = None,
        blocked_by_task_id: int | None = None,
        target_branch: str | None = None,
    ) -> str:
        """Delegate a child task with parent-linking, auto-inheritance, and depth guard.

        Use this for follow-up tasks after a parent completes/fails, retries, or
        synthesis steps that join multiple parent outputs. Requires at least one
        parent — errors if neither parent_task_ids nor TRIGGER_TASK_ID resolves.

        Key behaviors:
        - Requires parent (fail-loud on orphans — no silent root creation)
        - Auto-inherits card_id, target_branch, project from primary parent (unless overridden)
        - Depth guard: enforces root metadata.max_depth
        - Context injection: for multi-parent joins, prepends parent summaries into prompt
        - TRIGGER_TASK_ID auto-linking: reads from env var if parent_task_ids not explicit

        Args:
            brother: Worker name (e.g. "oppy").
            prompt: The task prompt/instructions.
            subject: Short description of the task.
            parent_task_ids: Explicit parent task IDs (1 or more). Single parent is common; multiple parents represent a join/synthesis step. If not provided, reads from TRIGGER_TASK_ID env var.
            working_dir: Override the worker's default working directory. NOT auto-inherited (machine-specific).
            max_turns: Optional maximum Claude turns.
            card_id: Optional kanban card ID. Auto-inherited from primary parent if not set.
            on_complete: Optional follow-up instructions for the Conductor.
            blocked_by_task_id: Optional task ID that must complete first.
            target_branch: Optional git branch. Auto-inherited from primary parent if not set.
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

        # Resolve parent_task_ids: explicit > TRIGGER_TASK_ID env > error
        resolved_parent_ids: list[int] = []
        if parent_task_ids is not None and len(parent_task_ids) > 0:
            resolved_parent_ids = list(parent_task_ids)
            logger.info(
                "delegate_child_task: explicit parent_task_ids=%s provided",
                resolved_parent_ids,
            )
        else:
            trigger_id = os.environ.get("TRIGGER_TASK_ID", "")
            if trigger_id:
                try:
                    resolved_parent_ids = [int(trigger_id)]
                    logger.info(
                        "delegate_child_task: auto-linked parent_task_ids=[%d] from TRIGGER_TASK_ID env",
                        resolved_parent_ids[0],
                    )
                except (ValueError, TypeError):
                    logger.warning(
                        "delegate_child_task: TRIGGER_TASK_ID has invalid value '%s'",
                        trigger_id,
                    )

        if not resolved_parent_ids:
            return (
                "Error: delegate_child_task requires a parent. "
                "Provide parent_task_ids or ensure TRIGGER_TASK_ID is set. "
                "Use delegate_task instead for root/initiative tasks."
            )

        # Fetch parent task(s) for inheritance and depth guard
        parent_tasks: list[dict] = []
        for pid in resolved_parent_ids:
            try:
                parent = await mailbox.get_task(pid)
                parent_tasks.append(parent)
            except Exception as e:
                return f"Error fetching parent task #{pid}: {e}"

        primary_parent = parent_tasks[0]

        # Auto-inherit from primary parent (unless explicitly overridden)
        inherited_project = primary_parent.get("project")
        inherited_card_id = card_id
        inherited_target_branch = target_branch

        if inherited_card_id is None:
            # Inherit card_id from primary parent's linked cards
            linked_cards = primary_parent.get("linked_cards", [])
            if linked_cards:
                inherited_card_id = linked_cards[0].get("id")

        if inherited_target_branch is None:
            # target_branch isn't stored on tasks directly, but is in the prompt context.
            # We inherit it if the parent has it (checking working_dir for branch hints).
            # Actually, target_branch is not persisted on task records. Skip inheritance.
            pass

        # Depth guard: check root metadata.max_depth
        root_task_id = primary_parent.get("root_task_id")
        max_parent_depth = max(p.get("depth", 0) for p in parent_tasks)
        child_depth = max_parent_depth + 1

        if root_task_id:
            try:
                root_task = await mailbox.get_task(root_task_id)
                root_metadata = root_task.get("metadata") or {}
                max_depth = root_metadata.get("max_depth")
                if max_depth is not None and child_depth > max_depth:
                    return (
                        f"Depth guard: child would be at depth {child_depth}, "
                        f"but root task #{root_task_id} has max_depth={max_depth}. "
                        f"Cannot create deeper tasks."
                    )
            except Exception as e:
                logger.warning("Failed to fetch root task #%d for depth guard: %s", root_task_id, e)

        # Context injection for multi-parent joins
        augmented_prompt = prompt
        if len(parent_tasks) > 1:
            context_lines = ["## Parent Task Context (for synthesis)\n"]
            for pt in parent_tasks:
                pt_subject = pt.get("subject", "(no subject)")
                pt_output = pt.get("output", "(no output)")
                pt_status = pt.get("status", "unknown")
                context_lines.append(
                    f"### Parent #{pt['id']}: {pt_subject} [{pt_status}]\n{pt_output}\n"
                )
            context_block = "\n".join(context_lines)
            augmented_prompt = f"{context_block}\n---\n\n{prompt}"

        # Resolve working_dir early so it's persisted on the task record.
        # Resolution order: explicit override > project mapping > worker default
        wd = working_dir
        if wd is None and inherited_project:
            project_dirs = worker.get("projects") or {}
            wd = project_dirs.get(inherited_project)
        if wd is None:
            wd = worker.get("working_dir")

        # Create task in Hearth with multi-parent support
        try:
            task_result = await mailbox.create_task(
                assignee=brother,
                prompt=augmented_prompt,
                subject=subject,
                parent_task_ids=resolved_parent_ids,
                working_dir=wd,
                on_complete=on_complete,
                blocked_by_task_id=blocked_by_task_id,
                max_turns=max_turns,
                project=inherited_project,
            )
            task_id = task_result["id"]
        except Exception as e:
            return f"Error creating task in Hearth: {e}"

        # Link task to card if card_id resolved (explicit or inherited)
        if inherited_card_id is not None:
            try:
                await mailbox.add_card_link(inherited_card_id, "task", str(task_id))
            except Exception:
                pass  # Non-fatal

        # Check if actually blocked
        actual_blocked_by = task_result.get("blocked_by_task_id")
        if actual_blocked_by is not None:
            result_lines = [
                f"Task #{task_id} created (deferred — blocked by #{actual_blocked_by}).",
                f"  Subject: {subject or '(none)'}",
                f"  Assignee: {brother}",
                f"  Parents: {resolved_parent_ids}",
                f"  Depth: {child_depth}",
                f"  Status: pending (waiting for #{actual_blocked_by} to complete)",
            ]
            if inherited_card_id is not None:
                result_lines.append(f"  Linked to card: #{inherited_card_id}")
            return "\n".join(result_lines)

        result = await _delegate_to_ember(
            brother=brother,
            prompt=augmented_prompt,
            subject=subject,
            task_id=task_id,
            working_dir=working_dir,
            max_turns=max_turns,
            target_branch=inherited_target_branch,
            card_id=inherited_card_id,
            project=inherited_project,
        )

        # Append parent info to result
        if not result.startswith("Task #") or "failed" in result.lower():
            return result
        return result + f"\n  Parents: {resolved_parent_ids}\n  Depth: {child_depth}"

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
            client, warnings = await _get_ember_client(name)
            if client is None:
                lines.append(f"{name}: No Ember configured")
                continue
            try:
                result = await client.health()
                entry_lines = [
                    f"{name}: Healthy",
                    f"  Active tasks: {result.get('active_tasks', '?')}",
                    f"  Uptime: {result.get('uptime_seconds', '?')}s",
                ]
                if warnings:
                    entry_lines.append(f"  Note: {'; '.join(warnings)}")
                lines.append("\n".join(entry_lines))
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
            client, _warnings = await _get_ember_client(name)
            if client is None:
                lines.append(f"{name}: No Ember configured")
                continue
            try:
                result = await client.active_tasks()
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
        "delegate_child_task": delegate_child_task,
        "check_worker_health": check_worker_health,
        "list_worker_tasks": list_worker_tasks,
    }
