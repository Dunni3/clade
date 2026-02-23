"""Ember server — HTTP listener for task execution on worker brothers.

A lightweight FastAPI server that accepts task execution requests and
launches Claude Code sessions in local tmux sessions.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field

from fastapi import Depends, FastAPI, HTTPException
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
class Aspen:
    """A single running Claude Code session on this Ember."""

    task_id: int | None
    session_name: str
    subject: str
    started_at: float
    working_dir: str | None = None


# Backward-compat alias
ActiveTask = Aspen


@dataclass
class AspenRegistry:
    """Tracks all running aspens (concurrent tasks). No DB — Hearth is source of truth."""

    _aspens: dict[str, Aspen] = field(default_factory=dict)
    _history: list[dict] = field(default_factory=list)

    def reap(self) -> None:
        """Remove aspens whose tmux sessions have died."""
        dead = [
            name for name, aspen in self._aspens.items()
            if not check_tmux_session(aspen.session_name)
        ]
        for name in dead:
            aspen = self._aspens.pop(name)
            self._history.append({
                "task_id": aspen.task_id,
                "session_name": aspen.session_name,
                "subject": aspen.subject,
                "started_at": aspen.started_at,
                "ended_at": time.time(),
            })

    def add(self, aspen: Aspen) -> None:
        """Register a new aspen."""
        self._aspens[aspen.session_name] = aspen

    def count(self) -> int:
        """Reap dead sessions and return active count."""
        self.reap()
        return len(self._aspens)

    def find_by_task_id(self, task_id: int) -> Aspen | None:
        """Find an aspen by its task_id. Linear scan."""
        for aspen in self._aspens.values():
            if aspen.task_id == task_id:
                return aspen
        return None

    def remove(self, session_name: str) -> Aspen | None:
        """Remove an aspen from the registry and record it in history."""
        aspen = self._aspens.pop(session_name, None)
        if aspen is not None:
            self._history.append({
                "task_id": aspen.task_id,
                "session_name": aspen.session_name,
                "subject": aspen.subject,
                "started_at": aspen.started_at,
                "ended_at": time.time(),
                "killed": True,
            })
        return aspen

    def list_info(self) -> list[dict]:
        """Reap dead sessions and return info dicts for all active aspens."""
        self.reap()
        return [
            {
                "task_id": a.task_id,
                "session_name": a.session_name,
                "subject": a.subject,
                "started_at": a.started_at,
                "working_dir": a.working_dir,
                "alive": check_tmux_session(a.session_name),
            }
            for a in self._aspens.values()
        ]


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class ExecuteTaskRequest(BaseModel):
    prompt: str
    subject: str = ""
    task_id: int | None = None
    working_dir: str | None = None
    max_turns: int | None = None
    hearth_url: str | None = None
    hearth_api_key: str | None = None
    hearth_name: str | None = None
    sender_name: str | None = None
    on_complete: str | None = None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_start_time = time.time()
_state = AspenRegistry()

_brother_name = os.environ.get("EMBER_BROTHER_NAME", "oppy")
_default_working_dir = os.environ.get("EMBER_WORKING_DIR")

app = FastAPI(title=f"Clade Ember ({_brother_name})")


@app.get("/health")
async def health():
    """Health check — unauthenticated."""
    return {
        "status": "ok",
        "brother": _brother_name,
        "active_tasks": _state.count(),
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@app.post("/tasks/execute", status_code=202)
async def execute_task(
    req: ExecuteTaskRequest,
    _token: str = Depends(verify_token),
):
    """Execute a task — launches Claude Code in a tmux session."""
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
            sender_name=req.sender_name or "unknown",
        )

    # Resolve Hearth connection for the spawned Claude session.
    # Fall back to Ember's own env vars when not provided in the request,
    # so the runner script always exports them explicitly (needed for hooks).
    hearth_url = req.hearth_url or os.environ.get("HEARTH_URL") or os.environ.get("MAILBOX_URL")
    hearth_api_key = req.hearth_api_key or os.environ.get("HEARTH_API_KEY") or os.environ.get("MAILBOX_API_KEY")
    hearth_name = req.hearth_name or os.environ.get("HEARTH_NAME") or os.environ.get("MAILBOX_NAME") or _brother_name

    # Launch
    result = launch_local_task(
        session_name=session_name,
        working_dir=wd,
        prompt=prompt,
        max_turns=req.max_turns,
        task_id=req.task_id,
        hearth_url=hearth_url,
        hearth_api_key=hearth_api_key,
        hearth_name=hearth_name,
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "launch_failed",
                "message": result.message,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )

    # Track aspen
    _state.add(Aspen(
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


@app.post("/tasks/{task_id}/kill")
async def kill_task(
    task_id: int,
    _token: str = Depends(verify_token),
):
    """Kill a running task by terminating its tmux session."""
    aspen = _state.find_by_task_id(task_id)
    if aspen is None:
        _state.reap()
        return {"status": "not_found", "task_id": task_id}

    session_name = aspen.session_name
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass  # Best-effort — session may already be dead

    _state.remove(session_name)
    return {"status": "killed", "session_name": session_name, "task_id": task_id}


@app.get("/tasks/active")
async def active_tasks(_token: str = Depends(verify_token)):
    """Get active task info and orphaned tmux sessions."""
    aspens = _state.list_info()
    active_names = {a["session_name"] for a in aspens}
    orphaned = [s for s in list_tmux_sessions(prefix="task-") if s not in active_names]

    return {
        "aspens": aspens,
        "orphaned_sessions": orphaned,
        # Backward compat: first aspen or None
        "active_task": aspens[0] if aspens else None,
    }


def main():
    """Entry point for clade-ember."""
    import uvicorn

    host = os.environ.get("EMBER_HOST", "0.0.0.0")
    port = int(os.environ.get("EMBER_PORT", "8100"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
