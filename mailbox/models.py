"""Pydantic request/response models for the mailbox API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# -- Requests --


class SendMessageRequest(BaseModel):
    recipients: list[str] = Field(..., min_length=1)
    subject: str = ""
    body: str


# -- Responses --


class MessageSummary(BaseModel):
    id: int
    sender: str
    subject: str
    body: str
    created_at: str
    is_read: bool


class ReadByEntry(BaseModel):
    brother: str
    read_at: str


class MessageDetail(BaseModel):
    id: int
    sender: str
    subject: str
    body: str
    created_at: str
    recipients: list[str]
    is_read: bool
    read_by: list[ReadByEntry] = []


class FeedMessage(BaseModel):
    id: int
    sender: str
    subject: str
    body: str
    created_at: str
    recipients: list[str]
    read_by: list[ReadByEntry]


class SendMessageResponse(BaseModel):
    id: int
    message: str = "Message sent"


class UnreadCountResponse(BaseModel):
    unread: int


class MarkReadResponse(BaseModel):
    message: str = "Marked as read"
