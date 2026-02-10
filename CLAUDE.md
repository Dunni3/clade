# Terminal Spawner MCP Server

An MCP server that lets Doot (Claude Code on Ian's local macOS laptop) spawn terminal windows, connect to brothers, communicate via a shared mailbox, and delegate tasks to remote Claude Code instances.

## Project Structure

```
terminal-spawner/
├── server.py                  # Doot's MCP server (terminal + mailbox + task tools)
├── mailbox_mcp.py             # Brothers' MCP server (mailbox + task tools only)
├── brothers.py                # Brother definitions (host, working_dir, description)
├── terminal.py                # AppleScript terminal spawning logic
├── ssh_task.py                # SSH + tmux task delegation (build_remote_script, initiate_task)
├── mailbox_client.py          # HTTP client for mailbox API
├── timestamp_utils.py         # Timezone-aware timestamp formatting
├── mailbox/                   # Mailbox API server (FastAPI + SQLite, deployed on EC2)
│   ├── app.py                 # FastAPI routes (/api/v1/messages, /api/v1/tasks, etc.)
│   ├── db.py                  # SQLite database (messages + tasks tables)
│   ├── auth.py                # API key authentication
│   ├── models.py              # Pydantic request/response models
│   └── config.py              # Server configuration
├── src/terminal_spawner/      # Packaged module (v0.2 refactoring)
│   ├── core/                  # Config, types
│   ├── terminal/              # AppleScript execution
│   ├── communication/         # Mailbox client (packaged version)
│   ├── mcp/
│   │   ├── server_full.py     # Full MCP server (Doot — terminal + mailbox)
│   │   ├── server_lite.py     # Lite MCP server (brothers — mailbox only)
│   │   └── tools/
│   │       ├── terminal_tools.py   # spawn_terminal, connect_to_brother
│   │       └── mailbox_tools.py    # send/check/read/browse/unread + task tools
│   └── web/                   # Web app backend (unused currently)
├── frontend/                  # Mailbox web UI (Vite + React + TypeScript + Tailwind v4)
├── deploy/                    # EC2 deployment scripts
│   ├── setup.sh               # Server provisioning
│   └── ec2.sh                 # Instance management (start/stop/status/ssh)
├── tests/                     # Packaged module tests
├── test_terminal_spawner.py   # Top-level terminal spawner tests (38 tests)
├── test_mailbox.py            # Top-level mailbox tests (89 tests)
├── test_ssh_task.py           # SSH task delegation tests
├── research_notes/            # Development logs and research (gitignored)
├── docs/                      # Documentation
└── BROTHER_MAILBOX_SETUP.md   # Self-setup guide for brothers
```

**Two server variants exist:**
- `server.py` — Doot's full MCP server: terminal spawning + mailbox + task delegation
- `mailbox_mcp.py` — Brothers' lite MCP server: mailbox + task visibility/updates only
- `src/terminal_spawner/mcp/server_lite.py` — Packaged version of the lite server (what brothers actually run via their `~/.claude.json`)

## MCP Tools

### Doot's tools (server.py)
- `spawn_terminal(command?, app?)` — Open Terminal.app window, optionally run a command
- `connect_to_brother(name)` — SSH + Claude Code session to oppy or jerry
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `initiate_ssh_task(brother, prompt, subject?, max_turns?, auto_pull?)` — Delegate a task via SSH + tmux
- `list_tasks(assignee?, status?, limit?)` — Browse tasks

### Brothers' tools (mailbox_mcp.py / server_lite)
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

Key file: `ssh_task.py` — contains `build_remote_script()`, `wrap_prompt()`, `initiate_task()`

## Mailbox System

- **API server:** FastAPI + SQLite on EC2 (`54.84.119.14`, HTTPS on 443)
- **Web UI:** React SPA at `https://54.84.119.14` (source in `frontend/`)
- **4 members:** ian, doot, oppy, jerry — each with their own API key
- **Admins:** ian and doot can edit/delete any message; others only their own

## Testing

```bash
# Run all tests (from project root, in terminal-spawner conda env)
python -m pytest tests/ test_terminal_spawner.py test_mailbox.py test_ssh_task.py -q
```

137 tests total across all files.

**Important:** When mocking httpx responses in tests, use `MagicMock` (not `AsyncMock`) since `.json()` and `.raise_for_status()` are sync methods.

## Deployment

- **EC2 host:** `54.84.119.14` (Elastic IP, instance `i-049a5a49e7068655b`)
- **Management:** `deploy/ec2.sh {start|stop|status|ssh}`
- **Service:** `sudo systemctl restart mailbox` on EC2
- **Web UI deploy:** `frontend/` -> `npm run build` -> SCP `dist/` to `/var/www/mailbox/` on EC2

## Key Gotchas

- **MCP server is a subprocess** — code changes require Claude Code restart to take effect
- **Two module systems coexist:** Top-level files (`server.py`, `mailbox_mcp.py`) and packaged modules (`src/terminal_spawner/`). Brothers run `server_lite` which imports from the packaged modules — new tools must be added to **both** places
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
