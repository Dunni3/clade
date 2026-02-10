"""Pydantic request/response models for the mailbox API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# -- Requests --


class SendMessageRequest(BaseModel):
    recipients: list[str] = Field(..., min_length=1)
    subject: str = ""
    body: str
    task_id: int | None = None


class EditMessageRequest(BaseModel):
    subject: str | None = None
    body: str | None = None


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


# -- Tasks --


class CreateTaskRequest(BaseModel):
    assignee: str
    subject: str = ""
    prompt: str
    session_name: str | None = None
    host: str | None = None
    working_dir: str | None = None


class UpdateTaskRequest(BaseModel):
    status: str | None = None
    output: str | None = None


class TaskSummary(BaseModel):
    id: int
    creator: str
    assignee: str
    subject: str
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class TaskDetail(TaskSummary):
    prompt: str
    session_name: str | None = None
    host: str | None = None
    working_dir: str | None = None
    output: str | None = None
    messages: list[FeedMessage] = []


class CreateTaskResponse(BaseModel):
    id: int
    message: str = "Task created"
