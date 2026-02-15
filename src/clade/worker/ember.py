"""Ember server — HTTP listener for task execution on worker brothers.

A lightweight FastAPI server that accepts task execution requests and
launches Claude Code sessions in local tmux sessions.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .auth import verify_token
from .runner import (
    check_tmux_session,
    launch_local_task,
    list_tmux_sessions,
    wrap_prompt,
)

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------


@dataclass
class ActiveTask:
    task_id: int | None
    session_name: str
    subject: str
    started_at: float
    working_dir: str | None = None


@dataclass
class TaskState:
    """Tracks the currently running task. No DB — Hearth is source of truth."""

    active: ActiveTask | None = None
    _history: list[dict] = field(default_factory=list)

    def is_busy(self) -> bool:
        """Check if there's an active task. Auto-clears stale tasks."""
        if self.active is None:
            return False
        if not check_tmux_session(self.active.session_name):
            # Session ended — clear it
            self._history.append({
                "task_id": self.active.task_id,
                "session_name": self.active.session_name,
                "subject": self.active.subject,
                "started_at": self.active.started_at,
                "ended_at": time.time(),
            })
            self.active = None
            return False
        return True

    def set_active(self, task: ActiveTask) -> None:
        self.active = task

    def get_info(self) -> dict | None:
        if self.active is None:
            return None
        return {
            "task_id": self.active.task_id,
            "session_name": self.active.session_name,
            "subject": self.active.subject,
            "started_at": self.active.started_at,
            "working_dir": self.active.working_dir,
            "alive": check_tmux_session(self.active.session_name),
        }


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class ExecuteTaskRequest(BaseModel):
    prompt: str
    subject: str = ""
    task_id: int | None = None
    working_dir: str | None = None
    max_turns: int = 50
    hearth_url: str | None = None
    hearth_api_key: str | None = None
    hearth_name: str | None = None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_start_time = time.time()
_state = TaskState()

_brother_name = os.environ.get("EMBER_BROTHER_NAME", "oppy")
_default_working_dir = os.environ.get("EMBER_WORKING_DIR")

app = FastAPI(title=f"Clade Ember ({_brother_name})")


@app.get("/health")
async def health():
    """Health check — unauthenticated."""
    return {
        "status": "ok",
        "brother": _brother_name,
        "active_tasks": 1 if _state.is_busy() else 0,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@app.post("/tasks/execute", status_code=202)
async def execute_task(
    req: ExecuteTaskRequest,
    _token: str = Depends(verify_token),
):
    """Execute a task — launches Claude Code in a tmux session."""
    if _state.is_busy():
        active = _state.get_info()
        return {
            "error": "busy",
            "message": f"Already running task (session: {active['session_name']})",
            "active_task": active,
        }

    # Resolve working directory
    wd = req.working_dir or _default_working_dir

    # Generate session name
    from .runner import generate_session_name
    session_name = generate_session_name(_brother_name, req.subject)

    # Wrap prompt with task context if task_id provided
    prompt = req.prompt
    if req.task_id is not None:
        prompt = wrap_prompt(
            user_prompt=req.prompt,
            brother=_brother_name,
            subject=req.subject,
            task_id=req.task_id,
            sender_name="doot",
        )

    # Launch
    result = launch_local_task(
        session_name=session_name,
        working_dir=wd,
        prompt=prompt,
        max_turns=req.max_turns,
        task_id=req.task_id,
        hearth_url=req.hearth_url,
        hearth_api_key=req.hearth_api_key,
        hearth_name=req.hearth_name,
    )

    if not result.success:
        return {
            "error": "launch_failed",
            "message": result.message,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    # Track active task
    _state.set_active(ActiveTask(
        task_id=req.task_id,
        session_name=session_name,
        subject=req.subject,
        started_at=time.time(),
        working_dir=wd,
    ))

    return {
        "status": "launched",
        "session_name": session_name,
        "task_id": req.task_id,
        "message": result.message,
    }


@app.get("/tasks/active")
async def active_tasks(_token: str = Depends(verify_token)):
    """Get active task info and orphaned tmux sessions."""
    active = _state.get_info() if _state.is_busy() else None
    orphaned = list_tmux_sessions(prefix="task-")

    # Filter out the active session from orphaned list
    if active and active["session_name"] in orphaned:
        orphaned.remove(active["session_name"])

    return {
        "active_task": active,
        "orphaned_sessions": orphaned,
    }


def main():
    """Entry point for clade-ember."""
    import uvicorn

    host = os.environ.get("EMBER_HOST", "0.0.0.0")
    port = int(os.environ.get("EMBER_PORT", "8100"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
