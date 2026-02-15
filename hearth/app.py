"""FastAPI application for the Hearth — the Clade's shared communication hub."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import db
from .auth import ADMIN_NAMES, resolve_sender
from .models import (
    CreateTaskEventRequest,
    CreateTaskRequest,
    CreateTaskResponse,
    CreateThrumRequest,
    CreateThrumResponse,
    EditMessageRequest,
    FeedMessage,
    KeyInfo,
    MarkReadResponse,
    MessageDetail,
    MessageSummary,
    ReadByEntry,
    RegisterKeyRequest,
    RegisterKeyResponse,
    SendMessageRequest,
    SendMessageResponse,
    TaskDetail,
    TaskEvent,
    TaskSummary,
    ThrumDetail,
    ThrumSummary,
    UnreadCountResponse,
    UpdateTaskRequest,
    UpdateThrumRequest,
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


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/messages", response_model=SendMessageResponse)
async def send_message(
    req: SendMessageRequest,
    sender: str = Depends(resolve_sender),
):
    message_id = await db.insert_message(
        sender=sender,
        subject=req.subject,
        body=req.body,
        recipients=req.recipients,
        task_id=req.task_id,
    )
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
    task_id = await db.insert_task(
        creator=caller,
        assignee=req.assignee,
        subject=req.subject,
        prompt=req.prompt,
        session_name=req.session_name,
        host=req.host,
        working_dir=req.working_dir,
        thrum_id=req.thrum_id,
    )
    return CreateTaskResponse(id=task_id)


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

    kwargs: dict = {}
    if req.status is not None:
        kwargs["status"] = req.status
        if req.status == "in_progress" and task["started_at"] is None:
            kwargs["started_at"] = _now_utc()
        if req.status in ("completed", "failed"):
            kwargs["completed_at"] = _now_utc()
    if req.output is not None:
        kwargs["output"] = req.output

    updated = await db.update_task(task_id, **kwargs)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


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
# Thrum endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/thrums", response_model=CreateThrumResponse)
async def create_thrum(
    req: CreateThrumRequest,
    caller: str = Depends(resolve_sender),
):
    thrum_id = await db.insert_thrum(
        creator=caller,
        title=req.title,
        goal=req.goal,
        plan=req.plan,
        priority=req.priority,
    )
    return CreateThrumResponse(id=thrum_id)


@app.get("/api/v1/thrums", response_model=list[ThrumSummary])
async def list_thrums(
    status: str | None = None,
    creator: str | None = None,
    limit: int = 50,
    _caller: str = Depends(resolve_sender),
):
    return await db.get_thrums(status=status, creator=creator, limit=limit)


@app.get("/api/v1/thrums/{thrum_id}", response_model=ThrumDetail)
async def get_thrum(
    thrum_id: int,
    _caller: str = Depends(resolve_sender),
):
    thrum = await db.get_thrum(thrum_id)
    if thrum is None:
        raise HTTPException(status_code=404, detail="Thrum not found")
    return thrum


@app.patch("/api/v1/thrums/{thrum_id}", response_model=ThrumDetail)
async def update_thrum(
    thrum_id: int,
    req: UpdateThrumRequest,
    caller: str = Depends(resolve_sender),
):
    thrum = await db.get_thrum(thrum_id)
    if thrum is None:
        raise HTTPException(status_code=404, detail="Thrum not found")

    if thrum["creator"] != caller and caller not in ADMIN_NAMES:
        raise HTTPException(
            status_code=403, detail="Only creator or admin can update"
        )

    kwargs: dict = {}
    if req.status is not None:
        kwargs["status"] = req.status
        if req.status in ("planning", "active") and thrum["started_at"] is None:
            kwargs["started_at"] = _now_utc()
        if req.status in ("completed", "failed"):
            kwargs["completed_at"] = _now_utc()
    for field in ("title", "goal", "plan", "priority", "output"):
        value = getattr(req, field)
        if value is not None:
            kwargs[field] = value

    updated = await db.update_thrum(thrum_id, **kwargs)
    if updated is None:
        raise HTTPException(status_code=404, detail="Thrum not found")
    return updated


@app.delete("/api/v1/thrums/{thrum_id}", status_code=204)
async def delete_thrum(
    thrum_id: int,
    caller: str = Depends(resolve_sender),
):
    """Delete a thrum (admin only)."""
    if caller not in ADMIN_NAMES:
        raise HTTPException(status_code=403, detail="Admin only")

    thrum = await db.get_thrum(thrum_id)
    if thrum is None:
        raise HTTPException(status_code=404, detail="Thrum not found")

    await db.delete_thrum(thrum_id)
    return Response(status_code=204)
