"""FastAPI application for the Hearth — the Clade's shared communication hub."""

import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import db
from .auth import ADMIN_NAMES, resolve_sender
from .config import API_KEYS, CONDUCTOR_TICK_CMD, EMBER_URLS

logger = logging.getLogger(__name__)
from .models import (
    BrotherProject,
    CardSummary,
    CreateCardRequest,
    CreateMorselRequest,
    CreateTaskEventRequest,
    CreateTaskRequest,
    CreateTaskResponse,
    EditMessageRequest,
    EmberEntry,
    FeedMessage,
    KeyInfo,
    LinkedCardInfo,
    MarkReadResponse,
    MemberActivityResponse,
    MessageDetail,
    MessageSummary,
    MorselSummary,
    ReadByEntry,
    RegisterKeyRequest,
    RegisterKeyResponse,
    SearchResponse,
    SendMessageRequest,
    SendMessageResponse,
    TaskDetail,
    TaskEvent,
    TaskSummary,
    TreeNode,
    TreeSummary,
    UnreadCountResponse,
    UpdateCardRequest,
    UpdateTaskRequest,
    UpsertBrotherProjectRequest,
    UpsertEmberRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="The Hearth", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now_utc() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Column ordering for forward-only card sync
_COLUMN_ORDER = {"backlog": 0, "todo": 1, "in_progress": 2, "done": 3, "archived": 4}


async def _sync_linked_cards_to_in_progress(task_id: int, assignee: str) -> None:
    """When a task moves to in_progress, sync any linked kanban cards forward.

    Only cards in columns before in_progress (backlog, todo) are moved.
    Cards already in in_progress, done, or archived are left untouched.

    Note: The card's assignee is unconditionally set to the task's assignee,
    overwriting any existing card assignee. This ensures the card reflects
    who is actively working on it.
    """
    card_map = await db.get_cards_for_objects("task", [str(task_id)])
    cards = card_map.get(str(task_id), [])
    for card_info in cards:
        card_col = card_info.get("col", "")
        # Only sync forward: don't overwrite cards already in_progress, done, or archived
        if _COLUMN_ORDER.get(card_col, 0) < _COLUMN_ORDER["in_progress"]:
            await db.update_card(card_info["id"], col="in_progress", assignee=assignee)


def _maybe_trigger_conductor_tick(
    task_id: int | None = None, message_id: int | None = None
) -> None:
    """Fire-and-forget: spawn the conductor tick if configured."""
    if not CONDUCTOR_TICK_CMD:
        return
    try:
        cmd = CONDUCTOR_TICK_CMD
        if task_id is not None:
            cmd = f"{cmd} {task_id}"
        elif message_id is not None:
            cmd = f"{cmd} --message {message_id}"
        logger.info("Triggering conductor tick: %s", cmd)
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        logger.warning("Failed to trigger conductor tick", exc_info=True)


def _format_task_section(task: dict, label: str) -> str:
    """Format a single ancestor/blocker task as a context section."""
    task_id = task["id"]
    subject = task.get("subject") or "(no subject)"
    status = task.get("status", "unknown")
    output = task.get("output") or "(no output recorded)"
    return f"### {label}: Task #{task_id} — \"{subject}\"\nStatus: {status}\nOutput: {output}"


async def _build_ancestor_context(task_id: int, max_levels: int = 3) -> str:
    """Walk up the task tree and build a context summary for worker prompts.

    Collects output summaries from parent tasks (up to max_levels) and the
    blocked_by task, then formats them as a preamble to prepend to the prompt.
    """
    task = await db.get_task(task_id)
    if not task:
        return ""

    sections: list[str] = []
    seen: set[int] = set()

    # Include blocked_by task context
    blocked_by_id = task.get("blocked_by_task_id")
    if blocked_by_id:
        blocker = await db.get_task(blocked_by_id)
        if blocker:
            sections.append(_format_task_section(blocker, "Predecessor (blocking task)"))
            seen.add(blocked_by_id)

    # Walk parent chain
    labels = ["Parent", "Grandparent", "Great-grandparent"]
    current_id = task.get("parent_task_id")
    for i in range(max_levels):
        if current_id is None or current_id in seen:
            break
        ancestor = await db.get_task(current_id)
        if not ancestor:
            break
        label = labels[i] if i < len(labels) else f"Ancestor (depth {i + 1})"
        sections.append(_format_task_section(ancestor, label))
        seen.add(current_id)
        current_id = ancestor.get("parent_task_id")

    if not sections:
        return ""

    return "## Context from prior tasks\n\n" + "\n\n".join(sections) + "\n\n---\n\n"


async def _cascade_failure(failed_task_id: int) -> None:
    """When a task fails, cascade failure to any pending tasks blocked by it.

    Recursively fails downstream tasks so that if A blocks B blocks C,
    failing A will also fail B and C.
    """
    blocked_tasks = await db.get_tasks_blocked_by(failed_task_id)
    if not blocked_tasks:
        return

    for task in blocked_tasks:
        task_id = task["id"]
        await db.clear_blocked_by(task_id)
        await db.update_task(
            task_id,
            status="failed",
            output=f"Upstream task #{failed_task_id} failed",
            completed_at=_now_utc(),
        )
        # Recurse: cascade to anything blocked by this newly-failed task
        await _cascade_failure(task_id)


async def _unblock_and_delegate(completed_task_id: int) -> None:
    """When a task completes, find tasks blocked by it and delegate them via Ember."""
    blocked_tasks = await db.get_tasks_blocked_by(completed_task_id)
    if not blocked_tasks:
        return

    # Fetch Ember registry once, outside the loop
    db_embers = await db.get_embers()
    ember_url_map: dict[str, str] = {e["name"]: e["ember_url"] for e in db_embers}

    for task in blocked_tasks:
        assignee = task["assignee"]
        task_id = task["id"]

        # Enrich prompt with ancestor/blocker context BEFORE clearing blocked_by
        context = await _build_ancestor_context(task_id)
        enriched_prompt = context + task["prompt"] if context else task["prompt"]

        # Clear the blocked_by reference
        await db.clear_blocked_by(task_id)

        # Look up Ember URL: DB first, env fallback
        ember_url = ember_url_map.get(assignee) or EMBER_URLS.get(assignee)

        if not ember_url:
            logger.warning(
                "No Ember URL for assignee %s — cannot auto-delegate unblocked task #%d",
                assignee, task_id,
            )
            continue

        # Look up assignee's API key
        assignee_key = await db.get_api_key_for_name(assignee)
        if assignee_key is None:
            for key, name in API_KEYS.items():
                if name == assignee:
                    assignee_key = key
                    break

        if not assignee_key:
            logger.warning(
                "No API key for assignee %s — cannot auto-delegate unblocked task #%d",
                assignee, task_id,
            )
            continue

        # Resolve working_dir: explicit > project lookup > None
        wd = task.get("working_dir")
        if wd is None and task.get("project"):
            bp = await db.get_brother_project(assignee, task["project"])
            if bp:
                wd = bp["working_dir"]

        # Send to Ember
        try:
            payload: dict = {
                "prompt": enriched_prompt,
                "task_id": task_id,
                "subject": task["subject"] or "",
                "sender_name": task["creator"],
                "working_dir": wd,
            }
            if task.get("max_turns") is not None:
                payload["max_turns"] = task["max_turns"]
            async with httpx.AsyncClient(verify=False, timeout=30.0) as http_client:
                resp = await http_client.post(
                    f"{ember_url}/tasks/execute",
                    json=payload,
                    headers={"Authorization": f"Bearer {assignee_key}"},
                )
                resp.raise_for_status()
            await db.update_task(task_id, status="launched")
            logger.info(
                "Auto-delegated unblocked task #%d to %s (was blocked by #%d)",
                task_id, assignee, completed_task_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to auto-delegate unblocked task #%d: %s", task_id, e
            )
            await db.update_task(
                task_id, status="failed",
                output=f"Auto-delegation failed after unblock: {e}",
                completed_at=_now_utc(),
            )


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/messages", response_model=SendMessageResponse)
async def send_message(
    req: SendMessageRequest,
    sender: str = Depends(resolve_sender),
):
    # Validate that all recipients are registered members
    env_names = set(API_KEYS.values())
    db_names = await db.get_all_member_names()
    known_members = env_names | db_names
    unknown = [r for r in req.recipients if r not in known_members]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown recipient(s): {', '.join(unknown)}. "
            f"Known members: {', '.join(sorted(known_members))}",
        )

    message_id = await db.insert_message(
        sender=sender,
        subject=req.subject,
        body=req.body,
        recipients=req.recipients,
        task_id=req.task_id,
    )

    # Trigger conductor tick when kamaji receives a message (not from himself)
    if "kamaji" in req.recipients and sender != "kamaji":
        _maybe_trigger_conductor_tick(message_id=message_id)

    return SendMessageResponse(id=message_id)


@app.get("/api/v1/messages", response_model=list[MessageSummary])
async def list_messages(
    unread_only: bool = False,
    limit: int = 50,
    sender: str = Depends(resolve_sender),
):
    messages = await db.get_messages(
        recipient=sender, unread_only=unread_only, limit=limit
    )
    return messages


@app.get("/api/v1/messages/feed", response_model=list[FeedMessage])
async def get_feed(
    sender: str | None = None,
    recipient: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _caller: str = Depends(resolve_sender),
):
    messages = await db.get_feed(
        sender=sender, recipient=recipient, query=q, limit=limit, offset=offset
    )
    return messages


@app.get("/api/v1/messages/{message_id}", response_model=MessageDetail)
async def get_message(
    message_id: int,
    sender: str = Depends(resolve_sender),
):
    msg = await db.get_message(message_id, recipient=sender)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@app.post("/api/v1/messages/{message_id}/view", response_model=FeedMessage)
async def view_message(
    message_id: int,
    caller: str = Depends(resolve_sender),
):
    msg = await db.get_message_any(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    await db.record_read(message_id, caller)
    # Re-fetch to include the just-recorded read
    msg = await db.get_message_any(message_id)
    return msg


@app.post("/api/v1/messages/{message_id}/read", response_model=MarkReadResponse)
async def mark_read(
    message_id: int,
    sender: str = Depends(resolve_sender),
):
    updated = await db.mark_read(message_id, recipient=sender)
    if not updated:
        raise HTTPException(
            status_code=404, detail="Message not found or already read"
        )
    return MarkReadResponse()


@app.post("/api/v1/messages/{message_id}/unread", response_model=MarkReadResponse)
async def mark_unread(
    message_id: int,
    caller: str = Depends(resolve_sender),
):
    """Mark a message as unread for the caller."""
    msg = await db.get_message_any(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    await db.mark_unread(message_id, caller)
    return MarkReadResponse(message="Marked as unread")


@app.patch("/api/v1/messages/{message_id}", response_model=FeedMessage)
async def edit_message(
    message_id: int,
    edit_request: EditMessageRequest,
    caller: str = Depends(resolve_sender),
):
    """Edit a message (sender or Ian/doot only)."""
    msg = await db.get_message_any(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg["sender"] != caller and caller not in ADMIN_NAMES:
        raise HTTPException(
            status_code=403,
            detail="Only the sender or an admin can edit this message",
        )

    updated = await db.update_message(
        message_id,
        subject=edit_request.subject,
        body=edit_request.body,
    )
    return updated


@app.delete("/api/v1/messages/{message_id}", status_code=204)
async def delete_message(
    message_id: int,
    caller: str = Depends(resolve_sender),
):
    """Delete a message (sender or Ian/doot only)."""
    msg = await db.get_message_any(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg["sender"] != caller and caller not in ADMIN_NAMES:
        raise HTTPException(
            status_code=403,
            detail="Only the sender or an admin can delete this message",
        )

    deleted = await db.delete_message(message_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found")

    return Response(status_code=204)


@app.get("/api/v1/unread", response_model=UnreadCountResponse)
async def unread_count(
    sender: str = Depends(resolve_sender),
):
    count = await db.get_unread_count(recipient=sender)
    return UnreadCountResponse(unread=count)


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/tasks", response_model=CreateTaskResponse)
async def create_task(
    req: CreateTaskRequest,
    caller: str = Depends(resolve_sender),
):
    try:
        task_id = await db.insert_task(
            creator=caller,
            assignee=req.assignee,
            subject=req.subject,
            prompt=req.prompt,
            session_name=req.session_name,
            host=req.host,
            working_dir=req.working_dir,
            parent_task_id=req.parent_task_id,
            parent_task_ids=req.parent_task_ids,
            metadata=req.metadata,
            on_complete=req.on_complete,
            blocked_by_task_id=req.blocked_by_task_id,
            max_turns=req.max_turns,
            project=req.project,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Return actual blocked_by_task_id from DB (may differ from input if blocker
    # was already completed — insert_task auto-clears in that case)
    task = await db.get_task(task_id)
    return CreateTaskResponse(
        id=task_id,
        blocked_by_task_id=task["blocked_by_task_id"] if task else None,
    )


@app.get("/api/v1/tasks", response_model=list[TaskSummary])
async def list_tasks(
    assignee: str | None = None,
    status: str | None = None,
    creator: str | None = None,
    limit: int = 50,
    _caller: str = Depends(resolve_sender),
):
    tasks = await db.get_tasks(
        assignee=assignee, status=status, creator=creator, limit=limit
    )
    return tasks


@app.get("/api/v1/tasks/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: int,
    _caller: str = Depends(resolve_sender),
):
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/api/v1/tasks/{task_id}/context")
async def get_task_context(
    task_id: int,
    max_levels: int = 3,
    _caller: str = Depends(resolve_sender),
):
    """Return ancestor/blocker context for a task (used by delegation tools)."""
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    context = await _build_ancestor_context(task_id, max_levels=max_levels)
    return {"task_id": task_id, "context": context}


@app.post("/api/v1/tasks/{task_id}/log", response_model=TaskEvent)
async def log_task_event(
    task_id: int,
    req: CreateTaskEventRequest,
    _caller: str = Depends(resolve_sender),
):
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    event_id = await db.insert_task_event(
        task_id=task_id,
        event_type=req.event_type,
        summary=req.summary,
        tool_name=req.tool_name,
    )
    events = await db.get_task_events(task_id)
    # Return the just-inserted event
    for ev in events:
        if ev["id"] == event_id:
            return ev
    # Fallback (shouldn't happen)
    return {"id": event_id, "task_id": task_id, "event_type": req.event_type,
            "tool_name": req.tool_name, "summary": req.summary, "created_at": ""}


@app.patch("/api/v1/tasks/{task_id}", response_model=TaskDetail)
async def update_task(
    task_id: int,
    req: UpdateTaskRequest,
    caller: str = Depends(resolve_sender),
):
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Only assignee, creator, or admins can update
    if caller not in (task["assignee"], task["creator"]) and caller not in ADMIN_NAMES:
        raise HTTPException(
            status_code=403, detail="Only assignee, creator, or admin can update"
        )

    # Guard: prevent status changes on tasks already in a terminal state
    TERMINAL_STATES = {"completed", "failed", "killed"}
    if req.status is not None and task["status"] in TERMINAL_STATES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change status of task in terminal state '{task['status']}'"
        )

    # Handle parent_task_id reparenting
    if req.parent_task_id is not None:
        try:
            await db.update_task_parent(task_id, req.parent_task_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    kwargs: dict = {}
    if req.status is not None:
        kwargs["status"] = req.status
        if req.status == "in_progress" and task["started_at"] is None:
            kwargs["started_at"] = _now_utc()
        if req.status in ("completed", "failed", "killed"):
            kwargs["completed_at"] = _now_utc()
    if req.output is not None:
        kwargs["output"] = req.output

    if kwargs:
        updated = await db.update_task(task_id, **kwargs)
        if updated is None:
            raise HTTPException(status_code=404, detail="Task not found")
    else:
        # Re-fetch to pick up parent_task_id changes
        updated = await db.get_task(task_id)

    # Auto-sync linked kanban cards when task moves to in_progress
    if req.status == "in_progress":
        try:
            await _sync_linked_cards_to_in_progress(task_id, updated["assignee"])
        except Exception:
            logger.warning("Failed to sync linked cards for task %d", task_id, exc_info=True)

    # When a task completes, unblock any tasks waiting on it and trigger delegation
    if req.status == "completed":
        await _unblock_and_delegate(task_id)

    # When a task fails, cascade failure to any pending tasks blocked by it
    if req.status == "failed":
        await _cascade_failure(task_id)

    # Trigger conductor tick when any task reaches a terminal state
    # Note: "killed" is intentionally excluded — killed tasks must not trigger Kamaji
    if req.status in ("completed", "failed"):
        _maybe_trigger_conductor_tick(task_id=task_id)

    return updated


@app.post("/api/v1/tasks/{task_id}/kill", response_model=TaskDetail)
async def kill_task(
    task_id: int,
    caller: str = Depends(resolve_sender),
):
    """Kill a running task: terminate tmux session on Ember, mark killed in DB."""
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Auth: only creator, admins can kill
    if task["creator"] != caller and caller not in ADMIN_NAMES:
        raise HTTPException(
            status_code=403, detail="Only creator or admin can kill a task"
        )

    # Guard: only active tasks can be killed
    if task["status"] not in ("pending", "launched", "in_progress"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot kill task with status '{task['status']}'"
        )

    ember_detail = ""
    assignee = task["assignee"]

    # Look up Ember URL: DB first, env fallback
    ember_url = None
    db_embers = await db.get_embers()
    for entry in db_embers:
        if entry["name"] == assignee:
            ember_url = entry["ember_url"]
            break
    if ember_url is None:
        ember_url = EMBER_URLS.get(assignee)

    if ember_url:
        # Look up assignee's API key for Ember auth
        assignee_key = await db.get_api_key_for_name(assignee)
        if assignee_key is None:
            # Env fallback: search API_KEYS dict
            for key, name in API_KEYS.items():
                if name == assignee:
                    assignee_key = key
                    break

        if assignee_key:
            try:
                async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                    resp = await client.post(
                        f"{ember_url}/tasks/{task_id}/kill",
                        headers={"Authorization": f"Bearer {assignee_key}"},
                    )
                    ember_result = resp.json()
                    ember_detail = f"Ember: {ember_result.get('status', 'unknown')}"
            except Exception as e:
                ember_detail = f"Ember unreachable: {e}"
        else:
            ember_detail = "Ember: no API key found for assignee"
    else:
        ember_detail = "Ember: no URL configured for assignee"

    # Mark killed in DB regardless of Ember result
    output = f"Killed by {caller}. {ember_detail}".strip()
    updated = await db.update_task(
        task_id, status="killed", completed_at=_now_utc(), output=output
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Do NOT trigger conductor tick for killed tasks
    return updated


@app.post("/api/v1/tasks/{task_id}/retry", response_model=TaskDetail)
async def retry_task(
    task_id: int,
    caller: str = Depends(resolve_sender),
):
    """Retry a failed task: create a child task with the same prompt and send to Ember."""
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Auth: assignee, creator, or admins
    if caller not in (task["assignee"], task["creator"]) and caller not in ADMIN_NAMES:
        raise HTTPException(
            status_code=403, detail="Only assignee, creator, or admin can retry"
        )

    # Guard: only failed tasks can be retried
    if task["status"] != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot retry task with status '{task['status']}' — only failed tasks can be retried"
        )

    # Build retry subject
    child_count = await db.count_children(task_id)
    retry_num = child_count + 1
    original_subject = task["subject"] or "(no subject)"
    retry_subject = f"Retry #{retry_num}: {original_subject}"

    # Create child task
    try:
        child_id = await db.insert_task(
            creator=caller,
            assignee=task["assignee"],
            prompt=task["prompt"],
            subject=retry_subject,
            host=task.get("host"),
            working_dir=task.get("working_dir"),
            parent_task_id=task_id,
            on_complete=task.get("on_complete"),
            project=task.get("project"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Look up Ember URL: DB first, env fallback
    assignee = task["assignee"]
    ember_url = None
    db_embers = await db.get_embers()
    for entry in db_embers:
        if entry["name"] == assignee:
            ember_url = entry["ember_url"]
            break
    if ember_url is None:
        ember_url = EMBER_URLS.get(assignee)

    if not ember_url:
        # No Ember configured — mark child failed
        await db.update_task(
            child_id, status="failed",
            output=f"No Ember URL configured for {assignee}",
            completed_at=_now_utc(),
        )
        child = await db.get_task(child_id)
        raise HTTPException(
            status_code=422,
            detail=f"No Ember URL configured for {assignee}. Child task #{child_id} created but marked failed.",
        )

    # Look up assignee's API key for Ember auth
    assignee_key = await db.get_api_key_for_name(assignee)
    if assignee_key is None:
        for key, name in API_KEYS.items():
            if name == assignee:
                assignee_key = key
                break

    if not assignee_key:
        await db.update_task(
            child_id, status="failed",
            output=f"No API key found for {assignee}",
            completed_at=_now_utc(),
        )
        child = await db.get_task(child_id)
        raise HTTPException(
            status_code=422,
            detail=f"No API key found for {assignee}. Child task #{child_id} created but marked failed.",
        )

    # Resolve working_dir: explicit > project lookup > None
    wd = task.get("working_dir")
    if wd is None and task.get("project"):
        bp = await db.get_brother_project(assignee, task["project"])
        if bp:
            wd = bp["working_dir"]

    # Enrich prompt with ancestor context (child has parent_task_id → original task)
    context = await _build_ancestor_context(child_id)
    enriched_prompt = context + task["prompt"] if context else task["prompt"]

    # Send to Ember
    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as http_client:
            resp = await http_client.post(
                f"{ember_url}/tasks/execute",
                json={
                    "prompt": enriched_prompt,
                    "task_id": child_id,
                    "subject": retry_subject,
                    "sender_name": caller,
                    "working_dir": wd,
                },
                headers={"Authorization": f"Bearer {assignee_key}"},
            )
            resp.raise_for_status()
    except Exception as e:
        await db.update_task(
            child_id, status="failed",
            output=f"Ember request failed: {e}",
            completed_at=_now_utc(),
        )
        child = await db.get_task(child_id)
        raise HTTPException(
            status_code=502,
            detail=f"Ember request failed: {e}. Child task #{child_id} created but marked failed.",
        )

    # Mark child as launched
    await db.update_task(child_id, status="launched")
    child = await db.get_task(child_id)

    # Do NOT trigger conductor tick — retry is the follow-up action itself
    return child


# ---------------------------------------------------------------------------
# API Key registration endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/keys", response_model=RegisterKeyResponse, status_code=201)
async def register_key(
    req: RegisterKeyRequest,
    _caller: str = Depends(resolve_sender),
):
    """Register a new API key. Any authenticated user can register keys."""
    success = await db.insert_api_key(req.name, req.key)
    if not success:
        raise HTTPException(
            status_code=409,
            detail=f"Key name '{req.name}' or key value already exists",
        )
    return RegisterKeyResponse(name=req.name)


@app.get("/api/v1/keys", response_model=list[KeyInfo])
async def list_keys(
    _caller: str = Depends(resolve_sender),
):
    """List all registered API key names (never exposes key values)."""
    return await db.list_api_keys()


# ---------------------------------------------------------------------------
# Member activity endpoint
# ---------------------------------------------------------------------------


@app.get("/api/v1/members/activity", response_model=MemberActivityResponse)
async def member_activity(
    _caller: str = Depends(resolve_sender),
):
    env_names = list(API_KEYS.values())
    members = await db.get_member_activity(extra_names=env_names)
    return MemberActivityResponse(members=members)


# ---------------------------------------------------------------------------
# Ember status endpoint
# ---------------------------------------------------------------------------


@app.get("/api/v1/embers/status")
async def ember_status(
    _caller: str = Depends(resolve_sender),
):
    """Proxy health checks to known Ember servers (env + DB merged, DB wins)."""
    # Merge env-var entries with DB entries (DB wins on conflict)
    merged: dict[str, str] = dict(EMBER_URLS)
    db_embers = await db.get_embers()
    registry_info: dict[str, dict] = {}
    for entry in db_embers:
        merged[entry["name"]] = entry["ember_url"]
        registry_info[entry["name"]] = {
            "registered_status": entry.get("status", "offline"),
            "last_seen": entry.get("last_seen"),
        }

    if not merged:
        return {"embers": {}}

    async def _check(name: str, url: str) -> tuple[str, dict]:
        try:
            async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
                resp = await client.get(f"{url}/health")
                resp.raise_for_status()
                data = resp.json()
                result = {
                    "status": "ok",
                    "active_tasks": data.get("active_tasks", 0),
                    "uptime_seconds": data.get("uptime_seconds"),
                }
        except Exception:
            result = {"status": "unreachable"}
        # Merge registry info if available
        if name in registry_info:
            result["registered_status"] = registry_info[name]["registered_status"]
            result["last_seen"] = registry_info[name]["last_seen"]
        return name, result

    results = await asyncio.gather(*[
        _check(name, url) for name, url in merged.items()
    ])
    return {"embers": dict(results)}


@app.put("/api/v1/embers/{name}", response_model=EmberEntry)
async def upsert_ember(
    name: str,
    req: UpsertEmberRequest,
    _caller: str = Depends(resolve_sender),
):
    """Register or update an Ember URL."""
    entry = await db.upsert_ember(name, req.ember_url)
    return entry


@app.get("/api/v1/embers", response_model=list[EmberEntry])
async def list_embers(
    _caller: str = Depends(resolve_sender),
):
    """List all registered Ember entries."""
    return await db.get_embers()


@app.get("/api/v1/embers/{name}", response_model=EmberEntry)
async def get_ember(
    name: str,
    _caller: str = Depends(resolve_sender),
):
    """Get a single Ember entry by brother name."""
    entry = await db.get_ember(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No ember registered for '{name}'")
    return entry


@app.post("/api/v1/embers/{name}/offline", response_model=EmberEntry)
async def ember_offline(
    name: str,
    _caller: str = Depends(resolve_sender),
):
    """Mark an Ember as offline (called from SLURM cleanup trap)."""
    entry = await db.set_ember_offline(name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Ember not found")
    return entry


@app.delete("/api/v1/embers/{name}", status_code=204)
async def delete_ember(
    name: str,
    caller: str = Depends(resolve_sender),
):
    """Delete an Ember entry (admin only)."""
    if caller not in ADMIN_NAMES:
        raise HTTPException(status_code=403, detail="Admin only")
    deleted = await db.delete_ember(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ember not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Brother Projects endpoints
# ---------------------------------------------------------------------------


@app.put("/api/v1/brothers/{name}/projects/{project}", response_model=BrotherProject)
async def upsert_brother_project(
    name: str,
    project: str,
    req: UpsertBrotherProjectRequest,
    _caller: str = Depends(resolve_sender),
):
    """Register or update a project working directory for a brother."""
    entry = await db.upsert_brother_project(name, project, req.working_dir)
    return entry


@app.get("/api/v1/brothers/{name}/projects", response_model=list[BrotherProject])
async def list_brother_projects(
    name: str,
    _caller: str = Depends(resolve_sender),
):
    """List all project paths for a brother."""
    return await db.get_brother_projects(name)


@app.get("/api/v1/brothers/{name}/projects/{project}", response_model=BrotherProject)
async def get_brother_project(
    name: str,
    project: str,
    _caller: str = Depends(resolve_sender),
):
    """Get the working directory for a specific brother + project combination."""
    entry = await db.get_brother_project(name, project)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No project '{project}' registered for brother '{name}'",
        )
    return entry


# ---------------------------------------------------------------------------
# Task Tree endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/trees", response_model=list[TreeSummary])
async def list_trees(
    limit: int = 50,
    offset: int = 0,
    _caller: str = Depends(resolve_sender),
):
    return await db.get_trees(limit=limit, offset=offset)


@app.get("/api/v1/trees/{root_id}", response_model=TreeNode)
async def get_tree(
    root_id: int,
    _caller: str = Depends(resolve_sender),
):
    tree = await db.get_tree(root_id)
    if tree is None:
        raise HTTPException(status_code=404, detail="Tree not found")
    return tree


# ---------------------------------------------------------------------------
# Morsel endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/morsels", response_model=MorselSummary, status_code=201)
async def create_morsel(
    req: CreateMorselRequest,
    caller: str = Depends(resolve_sender),
):
    links = [{"object_type": l.object_type, "object_id": l.object_id} for l in req.links] if req.links else None
    morsel_id = await db.insert_morsel(
        creator=caller,
        body=req.body,
        tags=req.tags or None,
        links=links,
    )
    morsel = await db.get_morsel(morsel_id)
    return morsel


@app.get("/api/v1/morsels", response_model=list[MorselSummary])
async def list_morsels(
    creator: str | None = None,
    tag: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _caller: str = Depends(resolve_sender),
):
    return await db.get_morsels(
        creator=creator,
        tag=tag,
        object_type=object_type,
        object_id=object_id,
        limit=limit,
        offset=offset,
    )


@app.get("/api/v1/morsels/{morsel_id}", response_model=MorselSummary)
async def get_morsel(
    morsel_id: int,
    _caller: str = Depends(resolve_sender),
):
    morsel = await db.get_morsel(morsel_id)
    if morsel is None:
        raise HTTPException(status_code=404, detail="Morsel not found")
    return morsel


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------


@app.get("/api/v1/search", response_model=SearchResponse)
async def search(
    q: str = "",
    types: str | None = None,
    limit: int = 20,
    created_after: str | None = None,
    created_before: str | None = None,
    _caller: str = Depends(resolve_sender),
):
    """Full-text search across tasks, morsels, and cards."""
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query parameter 'q' must not be empty")

    entity_types = None
    if types:
        entity_types = [t.strip() for t in types.split(",")]
        invalid = [t for t in entity_types if t not in db.VALID_SEARCH_TYPES]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid type(s): {', '.join(invalid)}. "
                f"Valid types: {', '.join(sorted(db.VALID_SEARCH_TYPES))}",
            )

    try:
        results = await db.search(
            query=q,
            entity_types=entity_types,
            limit=limit,
            created_after=created_after,
            created_before=created_before,
        )
    except Exception as e:
        err = str(e)
        if "fts5: syntax error" in err.lower() or "malformed match expression" in err.lower():
            raise HTTPException(status_code=422, detail=f"Invalid search syntax: {err}")
        raise

    return SearchResponse(query=q, results=results, total=len(results))


# ---------------------------------------------------------------------------
# Kanban endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/kanban/cards/by-link", response_model=list[CardSummary])
async def get_cards_by_link(
    object_type: str,
    object_id: str,
    _caller: str = Depends(resolve_sender),
):
    """Get all cards that link to a specific object (reverse lookup)."""
    card_infos = await db.get_cards_for_objects(object_type, [object_id])
    card_ids = [c["id"] for c in card_infos.get(object_id, [])]
    if not card_ids:
        return []
    # Fetch full card details
    results = []
    for cid in card_ids:
        card = await db.get_card(cid)
        if card:
            results.append(card)
    return results


@app.post("/api/v1/kanban/cards", response_model=CardSummary, status_code=201)
async def create_card(
    req: CreateCardRequest,
    caller: str = Depends(resolve_sender),
):
    if req.col not in db.KANBAN_COLUMNS:
        raise HTTPException(status_code=422, detail=f"Invalid column '{req.col}'. Must be one of: {', '.join(sorted(db.KANBAN_COLUMNS))}")
    if req.priority not in db.KANBAN_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority '{req.priority}'. Must be one of: {', '.join(sorted(db.KANBAN_PRIORITIES))}")
    links = [{"object_type": l.object_type, "object_id": l.object_id} for l in req.links] if req.links else None
    card_id = await db.insert_card(
        creator=caller,
        title=req.title,
        description=req.description,
        col=req.col,
        priority=req.priority,
        assignee=req.assignee,
        labels=req.labels or None,
        links=links,
        project=req.project,
    )
    card = await db.get_card(card_id)
    return card


@app.get("/api/v1/kanban/cards", response_model=list[CardSummary])
async def list_cards(
    col: str | None = None,
    assignee: str | None = None,
    creator: str | None = None,
    priority: str | None = None,
    label: str | None = None,
    project: str | None = None,
    include_archived: bool = False,
    limit: int = 200,
    offset: int = 0,
    _caller: str = Depends(resolve_sender),
):
    return await db.get_cards(
        col=col,
        assignee=assignee,
        creator=creator,
        priority=priority,
        label=label,
        project=project,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@app.get("/api/v1/kanban/cards/{card_id}", response_model=CardSummary)
async def get_card_detail(
    card_id: int,
    _caller: str = Depends(resolve_sender),
):
    card = await db.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.patch("/api/v1/kanban/cards/{card_id}", response_model=CardSummary)
async def update_card(
    card_id: int,
    req: UpdateCardRequest,
    _caller: str = Depends(resolve_sender),
):
    card = await db.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    kwargs: dict = {}
    if req.title is not None:
        kwargs["title"] = req.title
    if req.description is not None:
        kwargs["description"] = req.description
    if req.col is not None:
        if req.col not in db.KANBAN_COLUMNS:
            raise HTTPException(status_code=422, detail=f"Invalid column '{req.col}'")
        kwargs["col"] = req.col
    if req.priority is not None:
        if req.priority not in db.KANBAN_PRIORITIES:
            raise HTTPException(status_code=422, detail=f"Invalid priority '{req.priority}'")
        kwargs["priority"] = req.priority
    if "assignee" in req.model_fields_set:
        kwargs["assignee"] = req.assignee
    if "project" in req.model_fields_set:
        kwargs["project"] = req.project
    if "labels" in req.model_fields_set:
        kwargs["labels"] = req.labels
    if "links" in req.model_fields_set:
        kwargs["links"] = [{"object_type": l.object_type, "object_id": l.object_id} for l in req.links] if req.links else []

    updated = await db.update_card(card_id, **kwargs)
    if updated is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return updated


@app.delete("/api/v1/kanban/cards/{card_id}", status_code=204)
async def delete_card(
    card_id: int,
    caller: str = Depends(resolve_sender),
):
    card = await db.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    if card["creator"] != caller and caller not in ADMIN_NAMES:
        raise HTTPException(
            status_code=403,
            detail="Only the creator or an admin can delete this card",
        )

    deleted = await db.delete_card(card_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Card not found")
    return Response(status_code=204)


