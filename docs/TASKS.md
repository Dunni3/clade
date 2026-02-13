# Task Delegation

Send tasks to remote brothers via SSH. The brother runs autonomously in a detached tmux session and reports back through the mailbox.

## Safety Warning

By default, `initiate_ssh_task` launches Claude Code with `--dangerously-skip-permissions`. This means the remote Claude session can:

- Read, write, and delete any files the SSH user has access to
- Run arbitrary shell commands (install packages, kill processes, modify system config)
- Make network requests, push to git remotes, etc.

**There is no human-in-the-loop approval for tool calls.** The brother executes autonomously until it finishes or hits the turn limit.

Mitigations:
- **`max_turns`** (default 50) — limits how long the session can run. Lower this for simple tasks.
- **`working_dir`** — scopes the brother to a specific directory (but doesn't prevent escape).
- **Monitor live** — attach to the tmux session (`ssh host -t "tmux attach -t <session>"`) to watch what's happening and `Ctrl-c` to kill if needed.
- **Review after** — check the mailbox for the brother's completion report before trusting the results.

This is appropriate for trusted environments where the remote hosts are your own machines. Do not use this to run untrusted prompts on shared or production systems.

## Overview

```
Doot (local)                    Remote Brother
     │                               │
     │  initiate_ssh_task("oppy",    │
     │    prompt="review the code")  │
     │                               │
     ├──→ create task in mailbox     │
     ├──→ SSH + tmux launch ────────→│ claude -p "<wrapped prompt>" --dangerously-skip-permissions
     │                               │   ├── sends "task received" message
     │                               │   ├── does the work
     │                               │   ├── sends "task done" message
     │                               │   └── update_task(status="completed")
     │                               │
     │  list_tasks()                 │
     │  check_mailbox()              │
     └──────────────────────────────→│
```

## MCP Tools

### `initiate_ssh_task` (Doot only)

Launch a task on a remote brother. Creates a task record in the mailbox, SSHes to the brother's host, and starts a Claude Code session in a detached tmux session.

```
initiate_ssh_task(
    brother: "jerry" | "oppy",   # which brother
    prompt: str,                  # task instructions
    subject: str = "",            # short description
    working_dir: str | None,      # override brother's default dir
    max_turns: int = 50,          # Claude turn limit
)
```

**Example:**
```
initiate_ssh_task(
    brother="oppy",
    prompt="Review the training config in configs/train.yaml. Check for any issues with learning rate scheduling and batch size. Send your findings back via the mailbox.",
    subject="Review training config",
)
```

**Returns:**
```
Task #7 launched successfully.
  Brother: oppy
  Host: masuda
  Session: task-oppy-review-training-config-1739145600
  Subject: Review training config
Brother oppy will report back via the mailbox.
```

The brother receives the prompt wrapped with task context and instructions to:
1. Confirm receipt via mailbox (linked to the task)
2. Do the work
3. Send status updates if running low on turns
4. Send a completion message
5. Update task status to completed/failed

### `list_tasks` (Doot only)

Check the status of tasks.

```
list_tasks(
    assignee: str | None,     # filter by brother
    status: str | None,       # filter by status
    limit: int = 20,
)
```

**Example:**
```
list_tasks(assignee="oppy")
```

**Returns:**
```
#7 [completed] Review training config
  Assignee: oppy | Creator: doot
  Created: Feb 9, 6:00 PM EST (3 hr ago)
  Completed: Feb 9, 6:25 PM EST (2 hr ago)

#8 [launched] Run ablation study
  Assignee: jerry | Creator: doot
  Created: Feb 9, 7:00 PM EST (2 hr ago)
```

**Task statuses:** `pending`, `launched`, `in_progress`, `completed`, `failed`

### `update_task` (Brothers only — in `server_lite`)

Brothers use this to mark tasks as in progress, completed, or failed.

```
update_task(
    task_id: int,
    status: str | None,      # "in_progress", "completed", "failed"
    output: str | None,       # summary of what was done
)
```

## Task-Linked Messages

Messages can be linked to a task by including `task_id` when sending. This lets you see all communication related to a task in one place.

The wrapped prompt instructs the brother to include `task_id` in their mailbox messages, so receipt confirmations, progress updates, and completion reports are all linked to the task.

## Task Events (Activity Log)

If the brother has the **task logger hook** installed (`hooks/task_logger.sh`), tool calls during a task session are logged as events to the Hearth API. This gives Doot and Ian live visibility into what the brother is doing without attaching to the tmux session.

Events are viewable in the web UI at `https://54.84.119.14` on the task detail page, and via the API at `GET /api/v1/tasks/{id}/events`.

Each event includes:
- **event_type** — `PostToolUse` or `Stop`
- **tool_name** — which tool was called (Bash, Edit, Write, Task)
- **summary** — human-readable description (e.g., `ran: pytest tests/`, `edited: src/main.py`, `Session ended`)

**Setup:** See [BROTHER_SETUP.md](BROTHER_SETUP.md#step-4-install-task-logger-hook-optional-but-recommended) — install the hook on each brother that will receive tasks.

## Monitoring a Running Task

### From Doot

```
# Check task status
list_tasks(assignee="oppy", status="launched")

# Check mailbox for updates from the brother
check_mailbox()
```

### From Ian (Web UI)

Visit `https://54.84.119.14` and click on a task to see its detail page with linked messages and live activity events (if the task logger hook is installed).

### From Ian (SSH)

```bash
# SSH to the host and attach to the tmux session
ssh masuda
tmux attach -t task-oppy-review-training-config-1739145600
```

To detach without stopping the task: `Ctrl-b d`

To list all tmux sessions: `tmux ls`

## API Endpoints

All endpoints require `Authorization: Bearer <api_key>`.

### `POST /api/v1/tasks`

Create a task.

```json
{
    "assignee": "oppy",
    "prompt": "Review the code",
    "subject": "Code review",
    "session_name": "task-oppy-review-123",
    "host": "masuda",
    "working_dir": "~/projects/test"
}
```

Response: `{"id": 1, "message": "Task created"}`

### `GET /api/v1/tasks`

List tasks. Query params: `assignee`, `status`, `creator`, `limit`.

### `GET /api/v1/tasks/{id}`

Get task detail including linked messages.

### `PATCH /api/v1/tasks/{id}`

Update task status/output. Requires assignee, creator, or admin auth.

```json
{"status": "completed", "output": "Reviewed config, found 2 issues"}
```

### `POST /api/v1/tasks/{id}/log`

Log a task event (used by the task logger hook).

```json
{"event_type": "PostToolUse", "tool_name": "Bash", "summary": "ran: pytest tests/"}
```

### `GET /api/v1/tasks/{id}/events`

Get all events for a task. Returns a list of timestamped activity entries.

## How It Works Internally

### Shell Escaping

The prompt is **base64-encoded** in Python and decoded on the remote host, completely avoiding shell escaping issues. The script is piped to `ssh host bash -s` via stdin, avoiding SSH argument escaping. A temp runner script avoids tmux quoting issues. Three layers of indirection, zero quoting bugs.

### Remote Script

When `initiate_ssh_task` fires, it:

1. Creates a task record in the mailbox
2. Base64-encodes the wrapped prompt
3. Builds a bash script that:
   - Decodes the prompt into a temp file
   - Writes a runner script that `cd`s to the working dir and calls `claude -p --dangerously-skip-permissions --max-turns N`
   - Launches the runner in a detached tmux session (`tmux new-session -d`)
4. Sends the script to the remote host via `ssh host bash -s`
5. Checks for `TASK_LAUNCHED` in stdout to confirm success
6. Updates task status to `launched` or `failed`

The tmux session persists after SSH disconnects. The runner script self-deletes after Claude finishes.

## Troubleshooting

### "Task failed to launch"

Check the error message for details. Common causes:
- **SSH connection failed**: Verify `ssh masuda` or `ssh cluster` works manually
- **tmux not installed**: Install tmux on the remote host
- **claude not found**: Ensure Claude Code is installed and in PATH (use `bash --login` to load profile)

### Brother doesn't report back

- The brother's Claude session may have hit the turn limit (`--max-turns`)
- Check if the tmux session is still running: `ssh masuda "tmux ls"`
- Attach to the session to see what's happening: `ssh masuda -t "tmux attach -t <session-name>"`

### Task stuck in "launched"

The brother hasn't called `update_task` yet. Either:
- The Claude session is still running (check tmux)
- The session ended without updating the task (check mailbox for messages)
- The brother's mailbox MCP tools aren't configured (no `update_task` tool available)

## Deprecation Notice

`spawn_terminal` and `connect_to_brother` still work for opening interactive terminal windows. For autonomous remote work, prefer `initiate_ssh_task` — it provides structured task tracking, avoids AppleScript/macOS dependencies, and the brother reports back automatically.
