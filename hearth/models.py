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
    parent_task_id: int | None = None
    on_complete: str | None = None
    blocked_by_task_id: int | None = None
    max_turns: int | None = None


class UpdateTaskRequest(BaseModel):
    status: str | None = None
    output: str | None = None
    parent_task_id: int | None = None


class TaskSummary(BaseModel):
    id: int
    creator: str
    assignee: str
    subject: str
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    parent_task_id: int | None = None
    root_task_id: int | None = None
    blocked_by_task_id: int | None = None


class LinkedCardInfo(BaseModel):
    id: int
    title: str
    col: str
    priority: str


class TaskDetail(TaskSummary):
    prompt: str
    session_name: str | None = None
    host: str | None = None
    working_dir: str | None = None
    output: str | None = None
    on_complete: str | None = None
    messages: list[FeedMessage] = []
    events: list["TaskEvent"] = []
    children: list[TaskSummary] = []
    blocked_tasks: list[TaskSummary] = []
    linked_cards: list[LinkedCardInfo] = []


class CreateTaskResponse(BaseModel):
    id: int
    message: str = "Task created"
    blocked_by_task_id: int | None = None


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


# -- Task Trees --


class TreeSummary(BaseModel):
    root_task_id: int
    subject: str
    creator: str
    created_at: str
    total_tasks: int
    completed: int
    failed: int
    in_progress: int
    pending: int
    killed: int = 0
    blocked: int = 0


class TreeNode(BaseModel):
    id: int
    creator: str
    assignee: str
    subject: str
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    parent_task_id: int | None = None
    root_task_id: int | None = None
    blocked_by_task_id: int | None = None
    prompt: str | None = None
    session_name: str | None = None
    host: str | None = None
    working_dir: str | None = None
    output: str | None = None
    on_complete: str | None = None
    children: list["TreeNode"] = []
    linked_cards: list[LinkedCardInfo] = []


TreeNode.model_rebuild()


# -- Morsels --


class MorselLink(BaseModel):
    object_type: str
    object_id: str


class CreateMorselRequest(BaseModel):
    body: str
    tags: list[str] = []
    links: list[MorselLink] = []


class MorselSummary(BaseModel):
    id: int
    creator: str
    body: str
    created_at: str
    tags: list[str] = []
    links: list[MorselLink] = []


# -- Embers (registry) --


class UpsertEmberRequest(BaseModel):
    ember_url: str


class EmberEntry(BaseModel):
    name: str
    ember_url: str
    created_at: str
    updated_at: str


# -- Kanban --


class CardLink(BaseModel):
    object_type: str  # "task", "morsel", "tree", "message", "card"
    object_id: str


class CreateCardRequest(BaseModel):
    title: str
    description: str = ""
    col: str = "backlog"
    priority: str = "normal"
    assignee: str | None = None
    labels: list[str] = []
    links: list[CardLink] = []
    project: str | None = None


class UpdateCardRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    col: str | None = None
    priority: str | None = None
    assignee: str | None = None
    labels: list[str] | None = None
    links: list[CardLink] | None = None
    project: str | None = None


class CardSummary(BaseModel):
    id: int
    title: str
    description: str
    col: str
    priority: str
    assignee: str | None = None
    creator: str
    created_at: str
    updated_at: str
    labels: list[str] = []
    links: list[CardLink] = []
    project: str | None = None
