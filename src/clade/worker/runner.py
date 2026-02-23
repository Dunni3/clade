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
    from ..templates import render_template

    # Write prompt to temp file
    prompt_fd, prompt_path = tempfile.mkstemp(
        prefix="claude_task_", suffix=".txt", dir="/tmp"
    )
    with os.fdopen(prompt_fd, "w") as f:
        f.write(prompt)

    # Build env exports log line (redacted key)
    env_exports = []
    if task_id is not None:
        env_exports.append(f"CLAUDE_TASK_ID={task_id}")
    if hearth_url:
        env_exports.append(f"HEARTH_URL={hearth_url}")
    if hearth_api_key:
        env_exports.append("HEARTH_API_KEY=<redacted>")
    if hearth_name:
        env_exports.append(f"HEARTH_NAME={hearth_name}")

    log_path = f"/tmp/claude_runner_{session_name}.log"
    content = render_template(
        "local_runner.sh.j2",
        session_name=session_name,
        working_dir=working_dir,
        prompt_path=prompt_path,
        max_turns=max_turns,
        task_id=task_id,
        hearth_url=hearth_url,
        hearth_api_key=hearth_api_key,
        hearth_name=hearth_name,
        env_exports_log=", ".join(env_exports) if env_exports else "",
        log_path=log_path,
    )

    runner_fd, runner_path = tempfile.mkstemp(
        prefix="claude_runner_", suffix=".sh", dir="/tmp"
    )
    with os.fdopen(runner_fd, "w") as f:
        f.write(content)
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
