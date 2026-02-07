"""FastAPI application for the brother mailbox system."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from . import db
from .auth import resolve_sender
from .models import (
    FeedMessage,
    MarkReadResponse,
    MessageDetail,
    MessageSummary,
    SendMessageRequest,
    SendMessageResponse,
    UnreadCountResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="Brother Mailbox", lifespan=lifespan)


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


@app.get("/api/v1/unread", response_model=UnreadCountResponse)
async def unread_count(
    sender: str = Depends(resolve_sender),
):
    count = await db.get_unread_count(recipient=sender)
    return UnreadCountResponse(unread=count)
