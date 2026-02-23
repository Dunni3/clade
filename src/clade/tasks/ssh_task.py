"""SSH + tmux task execution for remote brothers.

Launches a Claude Code session on a remote host via SSH, running inside a
detached tmux session. Zero macOS/AppleScript dependencies.
"""

from __future__ import annotations

import base64
import re
import subprocess
import time
from dataclasses import dataclass


@dataclass
class TaskResult:
    success: bool
    session_name: str
    host: str
    message: str
    stdout: str = ""
    stderr: str = ""


def generate_session_name(brother: str, subject: str = "") -> str:
    """Generate a unique tmux session name.

    Example: task-oppy-review-config-1738900000
    """
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:30] if subject else ""
    ts = int(time.time())
    parts = ["task", brother]
    if slug:
        parts.append(slug)
    parts.append(str(ts))
    return "-".join(parts)


def wrap_prompt(
    user_prompt: str,
    brother: str,
    subject: str,
    task_id: int,
    sender_name: str = "doot",
) -> str:
    """Inject task context and mailbox instructions into the user's prompt."""
    lines = [
        f"## Task #{task_id} from {sender_name}",
        "",
        f"**Subject:** {subject}" if subject else "",
        "",
        "### Instructions",
        "",
        user_prompt,
        "",
        "### Task Protocol",
        "",
        f"This is task #{task_id} assigned to you by {sender_name}.",
        "",
        "1. Send a mailbox message confirming receipt of this task. "
        f"Address it to {sender_name}. "
        f"Use `task_id={task_id}` when sending the message so it gets linked to this task.",
        "",
        f"2. Update your task status to 'in_progress' using `update_task` with task_id={task_id}.",
        "",
        "3. Do the work described above.",
        "",
        "4. When finished, send a completion message via mailbox "
        f"(with `task_id={task_id}`) describing what was done.",
        "",
        "5. Update your task status to 'completed' (or 'failed' if something went wrong) "
        f"using the `update_task` tool with task_id={task_id}. "
        "Include an output summary.",
    ]
    return "\n".join(line for line in lines if line is not None)


def _build_pull_block() -> str:
    """Return the auto-pull bash block for discovering and updating the clade repo."""
    return """\
# Discover clade repo and pull latest
MCP_REPO=""

# New format: packaged install (-m clade.mcp.server_lite)
PYTHON_CMD=$(python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.claude.json')))
for srv in cfg.get('mcpServers', {}).values():
    if any('clade' in str(a) for a in srv.get('args', [])):
        print(srv['command'])
        break
" 2>/dev/null)

if [ -n "$PYTHON_CMD" ]; then
    MCP_REPO=$("$PYTHON_CMD" -c "
from pathlib import Path
import clade
print(Path(clade.__file__).parents[2])
" 2>/dev/null)
fi

# Fallback: old format (mailbox_mcp.py file path)
if [ -z "$MCP_REPO" ]; then
    MCP_SCRIPT=$(sed -n 's/.*"\\([^"]*mailbox_mcp\\.py\\)".*/\\1/p' ~/.claude.json 2>/dev/null | head -1)
    if [ -n "$MCP_SCRIPT" ]; then
        MCP_REPO=$(dirname "$MCP_SCRIPT")
    fi
fi

if [ -n "$MCP_REPO" ] && [ -d "$MCP_REPO/.git" ]; then
    git -C "$MCP_REPO" checkout main 2>&1 || true
    git -C "$MCP_REPO" pull --ff-only 2>&1 || true
fi"""


def build_remote_script(
    session_name: str,
    working_dir: str | None,
    prompt_b64: str,
    max_turns: int | None = None,
    auto_pull: bool = False,
    task_id: int | None = None,
    mailbox_url: str | None = None,
    mailbox_api_key: str | None = None,
) -> str:
    """Build a bash script to run on the remote host via `ssh host bash -s`.

    The script:
    1. Optionally pulls latest MCP server code (discovered from ~/.claude.json)
    2. Decodes the base64 prompt into a temp file
    3. Writes a runner script that cd's and calls claude -p
    4. Launches the runner in a detached tmux session
    5. Prints TASK_LAUNCHED on success

    Uses a two-phase Jinja2 render: the inner runner is rendered as clean bash,
    then heredoc-escaped and embedded into the outer wrapper.
    """
    from ..templates import render_template, heredoc_escape

    cd_cmd = f"cd {working_dir} || exit 1" if working_dir else ":"
    has_trap = task_id is not None and mailbox_url and mailbox_api_key

    env_lines = ""
    if has_trap:
        env_lines = (
            f"export CLAUDE_TASK_ID={task_id}\n"
            f"export HEARTH_URL='{mailbox_url}'\n"
            f"export HEARTH_API_KEY='{mailbox_api_key}'"
        )

    # Phase 1: render inner runner as clean bash
    inner = render_template(
        "remote_inner_runner.sh.j2",
        env_lines=env_lines,
        has_trap=has_trap,
        cd_cmd=cd_cmd,
        claude_started_flag=has_trap,
        max_turns=max_turns,
        capture_exit=has_trap,
        # log_path deliberately omitted — remote runner has no LOGFILE
    )

    # Phase 2: heredoc-escape for embedding, preserving write-time vars
    escaped_inner = heredoc_escape(
        inner, preserve_vars=["PROMPT_FILE", "RUNNER"]
    )

    # Phase 3: render outer wrapper
    return render_template(
        "remote_wrapper.sh.j2",
        pull_block=_build_pull_block() if auto_pull else "",
        prompt_b64=prompt_b64,
        inner_runner_content=escaped_inner,
        session_name=session_name,
    )


def initiate_task(
    host: str,
    working_dir: str | None,
    prompt: str,
    session_name: str,
    max_turns: int | None = None,
    ssh_timeout: int = 30,
    auto_pull: bool = False,
    task_id: int | None = None,
    mailbox_url: str | None = None,
    mailbox_api_key: str | None = None,
) -> TaskResult:
    """SSH into host and launch a Claude task in a detached tmux session.

    Returns a TaskResult indicating success or failure.
    """
    prompt_b64 = base64.b64encode(prompt.encode()).decode()
    script = build_remote_script(
        session_name, working_dir, prompt_b64, max_turns, auto_pull,
        task_id=task_id, mailbox_url=mailbox_url, mailbox_api_key=mailbox_api_key,
    )

    try:
        result = subprocess.run(
            ["ssh", host, "bash", "-s"],
            input=script,
            capture_output=True,
            text=True,
            timeout=ssh_timeout,
        )
    except subprocess.TimeoutExpired:
        return TaskResult(
            success=False,
            session_name=session_name,
            host=host,
            message=f"SSH connection to {host} timed out after {ssh_timeout}s",
        )
    except Exception as e:
        return TaskResult(
            success=False,
            session_name=session_name,
            host=host,
            message=f"SSH error: {e}",
        )

    if "TASK_LAUNCHED" in result.stdout:
        return TaskResult(
            success=True,
            session_name=session_name,
            host=host,
            message=f"Task launched on {host} in tmux session '{session_name}'",
            stdout=result.stdout,
            stderr=result.stderr,
        )
    else:
        return TaskResult(
            success=False,
            session_name=session_name,
            host=host,
            message=f"Task launch failed on {host}",
            stdout=result.stdout,
            stderr=result.stderr,
        )
