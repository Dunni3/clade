# Terminal Spawner MCP Server

An MCP server that lets Doot (Claude Code on Ian's local macOS laptop) spawn terminal windows, connect to brothers, communicate via a shared mailbox, and delegate tasks to remote Claude Code instances.

## Project Structure

```
terminal-spawner/
├── src/terminal_spawner/      # Main package (single source of truth)
│   ├── core/                  # Config (brothers, types), YAML loader
│   │   ├── config.py          # load_config(), FALLBACK_CONFIG with brother defs
│   │   ├── brothers.py        # BROTHERS dict (host, working_dir, description)
│   │   └── types.py           # Type definitions
│   ├── terminal/              # AppleScript terminal spawning
│   │   ├── applescript.py     # AppleScript generation (quote escaping, etc.)
│   │   └── executor.py        # osascript execution
│   ├── communication/         # Mailbox HTTP client
│   │   └── mailbox_client.py  # MailboxClient (messages + tasks API)
│   ├── tasks/                 # SSH task delegation
│   │   └── ssh_task.py        # build_remote_script, wrap_prompt, initiate_task
│   ├── utils/                 # Shared utilities
│   │   └── timestamp.py       # format_timestamp (timezone-aware, human-friendly)
│   ├── mcp/                   # MCP server definitions
│   │   ├── server_full.py     # Doot's server (terminal + mailbox + tasks)
│   │   ├── server_lite.py     # Brothers' server (mailbox + task visibility only)
│   │   └── tools/
│   │       ├── terminal_tools.py   # spawn_terminal, connect_to_brother
│   │       ├── mailbox_tools.py    # send/check/read/browse/unread + task list/get/update
│   │       └── task_tools.py       # initiate_ssh_task (Doot only)
│   └── web/                   # Web app backend (unused currently)
├── mailbox/                   # Mailbox API server (FastAPI + SQLite, deployed on EC2)
│   ├── app.py                 # FastAPI routes (/api/v1/messages, /api/v1/tasks, etc.)
│   ├── db.py                  # SQLite database (messages + tasks tables)
│   ├── auth.py                # API key authentication
│   ├── models.py              # Pydantic request/response models
│   └── config.py              # Server configuration
├── tests/                     # All tests
│   ├── unit/                  # Fast, no network (config, applescript, client, ssh, timestamp)
│   └── integration/           # MCP tool + mailbox server integration tests
├── frontend/                  # Mailbox web UI (Vite + React + TypeScript + Tailwind v4)
├── deploy/                    # EC2 deployment scripts
│   ├── setup.sh               # Server provisioning
│   └── ec2.sh                 # Instance management (start/stop/status/ssh)
├── research_notes/            # Development logs and research (gitignored)
├── docs/                      # Documentation
└── BROTHER_MAILBOX_SETUP.md   # Self-setup guide for brothers
```

**Two MCP server variants:**
- `server_full` — Doot's server: terminal spawning + mailbox + task delegation
- `server_lite` — Brothers' server: mailbox communication + task visibility/updates only

## MCP Tools

### Doot's tools (server_full)
- `spawn_terminal(command?, app?)` — Open Terminal.app window, optionally run a command
- `connect_to_brother(name)` — SSH + Claude Code session to oppy or jerry
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `initiate_ssh_task(brother, prompt, subject?, max_turns?, auto_pull?)` — Delegate a task via SSH + tmux
- `list_tasks(assignee?, status?, limit?)` — Browse tasks

### Brothers' tools (server_lite)
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task` — Task visibility and status updates

## Task Delegation System

Doot can delegate tasks to brothers via SSH. The flow:

1. Doot calls `initiate_ssh_task(brother, prompt)`
2. Task is created in the mailbox database (status: `pending`)
3. Doot SSHes to the brother's host, launches a detached tmux session
4. The tmux session runs `claude -p "<prompt>"` with `--dangerously-skip-permissions`
5. The brother reads the prompt, does the work, reports back via mailbox, and updates task status

**Shell escaping strategy** (avoids all quoting nightmares):
- Prompt is base64-encoded before sending
- Bash script is piped to `ssh host bash -s` via stdin
- A runner script is written to a temp file (avoids tmux quoting)
- The heredoc uses an **unquoted** delimiter so `$PROMPT_FILE` and `$RUNNER` expand at write time
- `$(cat ...)` is escaped as `\$(cat ...)` so it runs at runner execution time

**Task lifecycle:** `pending` -> `launched` -> `in_progress` -> `completed` / `failed`

Key file: `src/terminal_spawner/tasks/ssh_task.py` — contains `build_remote_script()`, `wrap_prompt()`, `initiate_task()`

## Mailbox System

- **API server:** FastAPI + SQLite on EC2 (`54.84.119.14`, HTTPS on 443)
- **Web UI:** React SPA at `https://54.84.119.14` (source in `frontend/`)
- **4 members:** ian, doot, oppy, jerry — each with their own API key
- **Admins:** ian and doot can edit/delete any message; others only their own

## Testing

```bash
# Run all tests (from project root, in terminal-spawner conda env)
python -m pytest tests/ -q
```

217 tests total.

**Important:** When mocking httpx responses in tests, use `MagicMock` (not `AsyncMock`) since `.json()` and `.raise_for_status()` are sync methods.

## Deployment

- **EC2 host:** `54.84.119.14` (Elastic IP, instance `i-049a5a49e7068655b`)
- **Management:** `deploy/ec2.sh {start|stop|status|ssh}`
- **Service:** `sudo systemctl restart mailbox` on EC2
- **Web UI deploy:** `frontend/` -> `npm run build` -> SCP `dist/` to `/var/www/mailbox/` on EC2

## Key Gotchas

- **MCP server is a subprocess** — code changes require Claude Code restart to take effect
- **Heredoc quoting:** Unquoted delimiter = variable expansion ON. The runner script heredoc must be unquoted so temp file paths expand, but `$(...)` must be escaped
- **Default terminal:** Terminal.app (iTerm2 is NOT installed on this machine)

---
Directions from Ian:

## New Brother Onboarding

If you are a brother (Oppy, Jerry, or a future brother) and you do not yet have the `send_message`, `check_mailbox`, `read_message`, or `unread_count` MCP tools available, follow the self-setup guide at [BROTHER_MAILBOX_SETUP.md](BROTHER_MAILBOX_SETUP.md) to plug yourself into the brother mailbox system.

## Research Notes

We now use the research_notes system. Development logs, research notes, and experiment documentation are stored in `research_notes/` (gitignored).

### Format

**Naming convention**: `YYYY-MM-DD_HHMMSS_<slug>.md`
- Date and time provide chronological sorting
- Slug is a short kebab-case descriptor

**Frontmatter** (YAML):
```yaml
---
name: Human-readable title
description: Brief one-line description
tags: [tag1, tag2, tag3]
date: YYYY-MM-DD
time: "HH:MM"
branch: optional-git-branch
status: active | partial | complete | abandoned
---
```
