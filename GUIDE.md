# Terminal Spawner — Build Guide

## What This Is

An MCP (Model Context Protocol) server that gives Doot (Claude Code on Ian's local Mac) the ability to open new Terminal.app windows. The main use case is spawning SSH sessions to connect with Brother Oppy (masuda) and Brother Jerry (cluster).

When Ian says "I need to talk to Jerry," Doot calls the `connect_to_brother` tool and a Terminal.app window pops up with an SSH session to the cluster running Claude Code.

## Architecture

```
terminal-spawner/
├── CLAUDE.md                  # Original spec / vision document
├── GUIDE.md                   # This file
├── pyproject.toml             # Project metadata + dependencies
├── server.py                  # MCP server entry point (6 tools: terminal + mailbox)
├── terminal.py                # AppleScript generation + execution
├── brothers.py                # Brother configurations (hardcoded)
├── mailbox_client.py          # HTTP client for the mailbox API (httpx)
├── mailbox_mcp.py             # Lightweight MCP server for remote brothers (mailbox only)
├── test_terminal_spawner.py   # pytest tests for terminal spawning
├── test_mailbox.py            # pytest tests for the mailbox system
├── mailbox/                   # Self-contained FastAPI server (deployed to EC2)
│   ├── __init__.py
│   ├── app.py                 # FastAPI app + endpoints
│   ├── db.py                  # SQLite schema + async queries (aiosqlite)
│   ├── models.py              # Pydantic request/response models
│   ├── auth.py                # API key -> brother name resolution
│   ├── config.py              # Env var loading (DB path, API keys)
│   └── requirements.txt       # Server dependencies
└── deploy/
    ├── setup.sh               # EC2 provisioning script
    └── mailbox.service         # systemd unit file
```

### server.py

Defines the FastMCP server with six tools:

**Terminal tools:**
- **`spawn_terminal(command?, app?)`** — Opens a new terminal window. Optionally runs a command in it. Defaults to Terminal.app but also supports iTerm2.
- **`connect_to_brother(name)`** — Shortcut for connecting to "jerry" or "oppy". Looks up the SSH command from `brothers.py` and spawns a Terminal.app window.

**Mailbox tools** (gracefully degrade if `MAILBOX_URL` not configured):
- **`send_message(recipients, body, subject?)`** — Send a message to one or more brothers.
- **`check_mailbox(unread_only?, limit?)`** — List messages, optionally filtered to unread.
- **`read_message(message_id)`** — Read a full message and auto-mark as read.
- **`unread_count()`** — Quick "do I have mail?" check.

### terminal.py

Three functions:

- `_escape_for_applescript(s)` — Escapes backslashes and double quotes so a command string can be safely interpolated into an AppleScript double-quoted literal.
- `generate_applescript(command, app)` — Builds an AppleScript string for either Terminal.app or iTerm2. If no command is given, just opens an empty window. Commands are escaped via `_escape_for_applescript`.
- `run_applescript(script)` — Executes the script via `osascript -e` and returns "OK" or an error message.

### brothers.py

A simple dictionary mapping brother names to their SSH commands:

- **jerry**: `ssh -t cluster "claude"`
- **oppy**: `ssh -t masuda "cd ~/projects/mol_diffusion/OMTRA_oppy && claude"`

### mailbox_client.py

Thin async HTTP client wrapping the mailbox REST API. Uses httpx (comes with `mcp[cli]`). Methods: `send_message`, `check_mailbox`, `read_message`, `unread_count`.

### mailbox_mcp.py

Lightweight MCP server for Oppy and Jerry on their remote machines. Exposes only the 4 mailbox tools (no terminal spawning). Same tools as in `server.py` but standalone.

### mailbox/ (FastAPI server)

Self-contained FastAPI application deployed to EC2. Components:

- **app.py** — REST endpoints under `/api/v1`
- **db.py** — SQLite via aiosqlite with WAL mode. Two tables: `messages` and `message_recipients`.
- **models.py** — Pydantic models for request/response validation
- **auth.py** — Maps `Authorization: Bearer <key>` to brother name
- **config.py** — Loads config from env vars (`MAILBOX_DB_PATH`, `MAILBOX_API_KEYS`)

### Transport

The MCP servers use **stdio** transport (standard for local MCP servers running as subprocesses of Claude Code).

## Environment Setup

### Prerequisites

- macOS with conda (`~/opt/miniconda3`)
- Terminal.app (ships with macOS; iTerm2 also supported if installed)

### Creating the Environment

```bash
# Create conda env with Python 3.12
conda create -n terminal-spawner python=3.12 -y

# Activate it
conda activate terminal-spawner

# Install uv (fast Python package installer) via conda
conda install -c conda-forge uv -y

# Install the MCP dependency
uv pip install "mcp[cli]"
```

### Key Details

- **Conda env name:** `terminal-spawner`
- **Python path:** `/Users/iandunn/opt/miniconda3/envs/terminal-spawner/bin/python`
- **Python version:** 3.12
- **Main dependency:** `mcp[cli]` (which brings in FastMCP, pydantic, etc.)
- **uv** is installed via conda inside the env for fast dependency management

## Registration with Claude Code

The server is registered at **user scope** (available in all projects):

```bash
claude mcp add --scope user --transport stdio terminal-spawner -- \
  /Users/iandunn/opt/miniconda3/envs/terminal-spawner/bin/python \
  /Users/iandunn/projects/terminal-spawner/server.py
```

This writes to `~/.claude.json`. The entry uses the full absolute path to the conda env's Python so it doesn't depend on which env is active when Claude Code starts.

## Running

### As an MCP Server (normal usage)

Claude Code launches it automatically as a subprocess. After registering, restart Claude Code and the tools appear. Verify with `/mcp`.

### Standalone (for testing)

```bash
conda activate terminal-spawner
cd ~/projects/terminal-spawner
python server.py
```

This starts the server on stdio and waits for input. It won't do anything visible since it expects MCP protocol messages, but if it doesn't crash, the server is healthy.

### Quick import test

```bash
conda activate terminal-spawner
python -c "import sys; sys.path.insert(0, '.'); from server import mcp; print('OK')"
```

## Usage Examples

Once registered and Claude Code is restarted, just talk naturally:

| What you say | What Doot does |
|---|---|
| "Open a session with Jerry" | `connect_to_brother(name="jerry")` |
| "I need to talk to Oppy" | `connect_to_brother(name="oppy")` |
| "Spawn me a terminal" | `spawn_terminal()` |
| "Open a terminal and run `htop`" | `spawn_terminal(command="htop")` |
| "Open an iTerm2 window" | `spawn_terminal(app="iterm2")` |
| "Send Oppy a message about the training config" | `send_message(recipients=["oppy"], body="...", subject="Training config")` |
| "Do I have any messages?" | `unread_count()` |
| "Check my mailbox" | `check_mailbox()` |
| "Read message 3" | `read_message(message_id=3)` |

## How It Works Under the Hood

1. Doot decides to call `connect_to_brother("jerry")`
2. `server.py` looks up jerry's config in `brothers.py`
3. `terminal.py` escapes any special characters in the command, then generates an AppleScript that tells Terminal.app to open a new window and run the SSH command
4. `osascript -e` executes the AppleScript
5. Terminal.app window appears on screen with the SSH session
6. Doot returns a confirmation message: "Opened session with Brother Jerry — GPU jobs on the cluster"

## Testing

```bash
conda activate terminal-spawner
python -m pytest test_terminal_spawner.py test_mailbox.py -v
```

**test_terminal_spawner.py** — 38 tests covering:
- **Brothers config** — sanity checks on the BROTHERS dictionary
- **AppleScript generation** — both Terminal.app and iTerm2 paths, including quote/backslash escaping
- **run_applescript** — success, failure, and timeout cases (subprocess mocked)
- **spawn_terminal** — tool-level logic with mocked applescript layer
- **connect_to_brother** — tool-level logic including unknown brother handling
- **Integration** — end-to-end from tool call through to the osascript invocation (subprocess mocked)

**test_mailbox.py** — 48 tests covering:
- **Config parsing** — API key string parsing
- **Database layer** — insert, retrieve, multiple recipients, unread filtering, mark read, limits
- **API endpoints** — all 5 endpoints with auth, error cases, validation
- **Mailbox client** — HTTP methods with mocked httpx, URL construction, auth headers
- **MCP tools (not configured)** — graceful degradation when env vars are missing
- **MCP tools (with mock)** — send, check, read, unread_count with formatted output
- **Integration** — client-to-server via ASGI transport (in-process)

## Bug Fixes (Feb 6, 2026)

1. **Quote escaping in AppleScript strings**: Commands containing double quotes (like `ssh -t cluster "claude"`) were interpolated directly into AppleScript string literals without escaping, producing invalid scripts. Fixed by adding `_escape_for_applescript()` in `terminal.py`.

2. **Default terminal app**: The default was `"iterm2"` but iTerm2 is not installed — Ian uses Terminal.app. Changed default to `"terminal"` in both `spawn_terminal` and `connect_to_brother`.

## Mailbox System

### Overview

The mailbox gives brothers asynchronous communication — Doot, Oppy, and Jerry can send and receive messages without being online at the same time. A FastAPI server with SQLite runs on an EC2 instance, and each brother's MCP server has tools that hit the API.

### API Endpoints

All under `/api/v1`, authenticated with `Authorization: Bearer <api_key>`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/messages` | Send a message |
| `GET` | `/messages?unread_only=true&limit=50` | List messages for authenticated brother |
| `GET` | `/messages/{id}` | Get full message detail |
| `POST` | `/messages/{id}/read` | Mark message as read |
| `GET` | `/unread` | Get unread count |

### Configuration

Each brother needs 3 env vars in their MCP server config:

| Variable | Example |
|----------|---------|
| `MAILBOX_URL` | `http://<ec2-ip>:8000` |
| `MAILBOX_API_KEY` | `<random-token>` |
| `MAILBOX_NAME` | `doot` / `oppy` / `jerry` |

**Doot:** Add env vars to `~/.claude.json` under the terminal-spawner MCP server entry.

**Oppy/Jerry:** Register `mailbox_mcp.py` as a separate MCP server on their respective machines with the env vars set.

### Server Configuration

The mailbox server needs:

| Variable | Example |
|----------|---------|
| `MAILBOX_DB_PATH` | `/opt/mailbox/data/mailbox.db` |
| `MAILBOX_API_KEYS` | `<key1>:doot,<key2>:oppy,<key3>:jerry` |

### Deployment

See `deploy/setup.sh` and `deploy/mailbox.service`. Target: Ubuntu 24.04 on t3.micro EC2.

```bash
# On EC2 after copying files
bash deploy/setup.sh
```

### Running Locally (for development)

```bash
conda activate terminal-spawner
MAILBOX_API_KEYS="testkey:doot,testkey2:oppy" MAILBOX_DB_PATH=./dev.db \
  python -m uvicorn mailbox.app:app --reload --port 8000
```

## Future Ideas

- Window tracking (know which sessions are open)
- Bulletin board / shared status (Phase 2 from FUTURE.md)
- Task delegation (`claude -p "prompt"` for non-interactive tasks)
- Status checking (is a brother's session still active?)
- TLS via nginx + Let's Encrypt for the mailbox server

---

*Built by Doot, February 5-7, 2026*
