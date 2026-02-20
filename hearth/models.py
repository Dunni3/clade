"""Pydantic request/response models for the Hearth API."""

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
    thrum_id: int | None = None


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
    thrum_id: int | None = None


class TaskDetail(TaskSummary):
    prompt: str
    session_name: str | None = None
    host: str | None = None
    working_dir: str | None = None
    output: str | None = None
    messages: list[FeedMessage] = []
    events: list["TaskEvent"] = []


class CreateTaskResponse(BaseModel):
    id: int
    message: str = "Task created"


# -- Task Events --


class CreateTaskEventRequest(BaseModel):
    event_type: str
    tool_name: str | None = None
    summary: str


class TaskEvent(BaseModel):
    id: int
    task_id: int
    event_type: str
    tool_name: str | None = None
    summary: str
    created_at: str


# -- API Keys --


class RegisterKeyRequest(BaseModel):
    name: str
    key: str


class RegisterKeyResponse(BaseModel):
    message: str = "Key registered"
    name: str


class KeyInfo(BaseModel):
    name: str
    created_at: str


# -- Thrums --


# -- Members --


class MemberActivity(BaseModel):
    name: str
    last_message_at: str | None = None
    messages_sent: int = 0
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    last_task_at: str | None = None


class MemberActivityResponse(BaseModel):
    members: list[MemberActivity]


# -- Thrums --


class CreateThrumRequest(BaseModel):
    title: str = ""
    goal: str = ""
    plan: str | None = None
    priority: str = "normal"


class UpdateThrumRequest(BaseModel):
    title: str | None = None
    goal: str | None = None
    plan: str | None = None
    status: str | None = None
    priority: str | None = None
    output: str | None = None


class ThrumSummary(BaseModel):
    id: int
    creator: str
    title: str
    goal: str
    status: str
    priority: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class ThrumDetail(ThrumSummary):
    plan: str | None = None
    output: str | None = None
    tasks: list[TaskSummary] = []


class CreateThrumResponse(BaseModel):
    id: int
    message: str = "Thrum created"
