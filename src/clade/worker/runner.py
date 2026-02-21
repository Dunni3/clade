"""Local tmux task launcher for Ember servers.

Launches Claude Code sessions in detached tmux sessions on the local machine.
Reuses session naming and prompt wrapping from ssh_task.py.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass

from ..tasks.ssh_task import generate_session_name, wrap_prompt  # noqa: F401 (re-export)


@dataclass
class LocalTaskResult:
    success: bool
    session_name: str
    message: str
    stdout: str = ""
    stderr: str = ""


def build_runner_script(
    session_name: str,
    working_dir: str | None,
    prompt: str,
    max_turns: int | None = None,
    task_id: int | None = None,
    hearth_url: str | None = None,
    hearth_api_key: str | None = None,
    hearth_name: str | None = None,
) -> tuple[str, str]:
    """Write prompt and runner script to temp files.

    Returns (prompt_file_path, runner_script_path).
    """
    # Write prompt to temp file
    prompt_fd, prompt_path = tempfile.mkstemp(
        prefix="claude_task_", suffix=".txt", dir="/tmp"
    )
    with os.fdopen(prompt_fd, "w") as f:
        f.write(prompt)

    # Build runner script with logging for debugging dead sessions
    log_path = f"/tmp/claude_runner_{session_name}.log"
    lines = ["#!/bin/bash"]

    # Log file for post-mortem debugging
    lines.append(f'LOGFILE="{log_path}"')
    lines.append('echo "$(date -Iseconds) runner started (pid $$)" > "$LOGFILE"')

    # Export env vars for Hearth access.
    # Each var is independent so callers can selectively override.
    # When launched via Ember, the process already inherits correct env vars;
    # only vars explicitly passed will be overridden.
    if task_id is not None:
        lines.append(f"export CLAUDE_TASK_ID={task_id}")
    if hearth_url:
        lines.append(f"export HEARTH_URL='{hearth_url}'")
    if hearth_api_key:
        lines.append(f"export HEARTH_API_KEY='{hearth_api_key}'")
    if hearth_name:
        lines.append(f"export HEARTH_NAME='{hearth_name}'")

    # Change to working directory
    if working_dir:
        lines.append(f"cd {working_dir} || exit 1")

    # Run Claude, capturing exit code
    lines.append('echo "$(date -Iseconds) launching claude" >> "$LOGFILE"')
    claude_cmd = f'claude -p "$(cat {prompt_path})" --dangerously-skip-permissions'
    if max_turns is not None:
        claude_cmd += f" --max-turns {max_turns}"
    lines.append(claude_cmd)
    lines.append('EXIT_CODE=$?')
    lines.append('echo "$(date -Iseconds) claude exited with code $EXIT_CODE" >> "$LOGFILE"')

    # Auto-mark task failed if session exits without brother updating status
    if task_id is not None:
        lines.append("")
        lines.append("# Auto-mark task failed if session exited without completing")
        lines.append('if [ -n "$CLAUDE_TASK_ID" ] && [ -n "$HEARTH_URL" ] && [ -n "$HEARTH_API_KEY" ]; then')
        lines.append('    curl -sf -X PATCH "$HEARTH_URL/api/v1/tasks/$CLAUDE_TASK_ID" \\')
        lines.append('        -H "Authorization: Bearer $HEARTH_API_KEY" \\')
        lines.append('        -H "Content-Type: application/json" \\')
        lines.append('        -d "{\\"status\\":\\"failed\\",\\"output\\":\\"Session exited with code $EXIT_CODE\\"}" \\')
        lines.append('        >/dev/null 2>&1 || true')
        lines.append("fi")

    # Self-cleanup (keep log on failure for debugging)
    lines.append(f'rm -f "{prompt_path}" "$0"')
    lines.append('[ "$EXIT_CODE" -eq 0 ] && rm -f "$LOGFILE"')

    runner_fd, runner_path = tempfile.mkstemp(
        prefix="claude_runner_", suffix=".sh", dir="/tmp"
    )
    with os.fdopen(runner_fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(runner_path, 0o755)

    return prompt_path, runner_path


def launch_local_task(
    session_name: str,
    working_dir: str | None,
    prompt: str,
    max_turns: int | None = None,
    task_id: int | None = None,
    hearth_url: str | None = None,
    hearth_api_key: str | None = None,
    hearth_name: str | None = None,
) -> LocalTaskResult:
    """Launch a Claude Code session in a detached tmux session.

    Returns a LocalTaskResult indicating success or failure.
    """
    prompt_path, runner_path = build_runner_script(
        session_name=session_name,
        working_dir=working_dir,
        prompt=prompt,
        max_turns=max_turns,
        task_id=task_id,
        hearth_url=hearth_url,
        hearth_api_key=hearth_api_key,
        hearth_name=hearth_name,
    )

    try:
        result = subprocess.run(
            [
                "tmux", "new-session", "-d",
                "-s", session_name,
                f"bash --login {runner_path}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        # Clean up on failure
        for path in (prompt_path, runner_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        return LocalTaskResult(
            success=False,
            session_name=session_name,
            message=f"Failed to launch tmux session: {e}",
        )

    if result.returncode != 0:
        # Clean up on failure
        for path in (prompt_path, runner_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        return LocalTaskResult(
            success=False,
            session_name=session_name,
            message=f"tmux exited with code {result.returncode}",
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return LocalTaskResult(
        success=True,
        session_name=session_name,
        message=f"Task launched in tmux session '{session_name}'",
        stdout=result.stdout,
        stderr=result.stderr,
    )


def check_tmux_session(session_name: str) -> bool:
    """Check if a tmux session exists."""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def list_tmux_sessions(prefix: str = "task-") -> list[str]:
    """List tmux sessions matching prefix."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        return [
            name.strip()
            for name in result.stdout.strip().split("\n")
            if name.strip().startswith(prefix)
        ]
    except Exception:
        return []
