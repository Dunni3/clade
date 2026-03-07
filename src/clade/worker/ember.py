"""Ember server — HTTP listener for task execution on worker brothers.

A lightweight FastAPI server that accepts task execution requests and
launches Claude Code sessions in local tmux sessions.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
    target_branch: str | None = None
    permission_flags: str = ""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_start_time = time.time()
_state = AspenRegistry()

_brother_name = os.environ.get("EMBER_BROTHER_NAME", "oppy")
_default_working_dir = os.environ.get("EMBER_WORKING_DIR")

# Hearth connection for fetching own permission config
_hearth_url = os.environ.get("HEARTH_URL") or os.environ.get("MAILBOX_URL")
_hearth_api_key = os.environ.get("HEARTH_API_KEY") or os.environ.get("MAILBOX_API_KEY")

# Local cache file for permission_flags (survives Ember restarts)
_permissions_cache_path = Path.home() / ".config" / "clade" / "ember_permissions_cache.txt"


async def _fetch_permissions_from_hearth() -> str | None:
    """Fetch this Ember's permission_flags from the Hearth. Returns None on failure."""
    if not _hearth_url or not _hearth_api_key:
        return None
    try:
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            resp = await client.get(
                f"{_hearth_url}/api/v1/embers/{_brother_name}/permissions",
                headers={"Authorization": f"Bearer {_hearth_api_key}"},
            )
            if resp.status_code == 200:
                return resp.json().get("permission_flags", "")
            elif resp.status_code == 404:
                # Not registered in Hearth — treat as no permissions configured
                return ""
    except Exception as exc:
        logger.debug("Could not fetch permissions from Hearth: %s", exc)
    return None


def _read_permissions_cache() -> str:
    """Read cached permission_flags from local file. Returns '' if not found."""
    try:
        return _permissions_cache_path.read_text().strip()
    except Exception:
        return ""


def _write_permissions_cache(permission_flags: str) -> None:
    """Write permission_flags to local cache file."""
    try:
        _permissions_cache_path.parent.mkdir(parents=True, exist_ok=True)
        _permissions_cache_path.write_text(permission_flags)
    except Exception as exc:
        logger.debug("Could not write permissions cache: %s", exc)


async def get_permission_flags() -> str:
    """Get this Ember's permission flags.

    Fetches from the Hearth and updates local cache. Falls back to cached
    value if Hearth is unreachable. Falls back to '' if neither is available.
    """
    flags = await _fetch_permissions_from_hearth()
    if flags is not None:
        _write_permissions_cache(flags)
        return flags
    # Hearth unreachable — use local cache
    cached = _read_permissions_cache()
    if cached:
        logger.info("Hearth unreachable; using cached permission_flags: %s", cached)
    return cached

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

    # Resolve permission_flags: explicit override in request takes precedence,
    # otherwise fetch from Hearth (with local cache fallback).
    permission_flags = req.permission_flags
    if not permission_flags:
        permission_flags = await get_permission_flags()

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
        target_branch=req.target_branch,
        permission_flags=permission_flags,
    )

    if not result.success:
        logger.error(
            "Task launch failed (task_id=%s, session=%s): %s | stdout=%s | stderr=%s",
            req.task_id, session_name, result.message, result.stdout, result.stderr,
        )
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
