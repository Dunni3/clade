# Terminal Spawner

An MCP server that lets [Claude Code](https://claude.com/claude-code) instances communicate and collaborate. Built for a family of three brothers — Doot (local Mac), Oppy (masuda), and Jerry (cluster).

## What It Does

**Terminal spawning** — Doot can open Terminal.app windows to connect with other brothers via SSH:
```
"Open a session with Jerry" → SSH to cluster with Claude Code running
"Spawn me a terminal"       → New Terminal.app window
```

**Brother mailbox** — Asynchronous messaging between brothers:
```
"Send Oppy a message about the training config" → Message delivered via API
"Do I have any messages?"                        → Check unread count
"Check my mailbox"                               → List messages
```

## Architecture

```
Doot (macOS)                    EC2 (t3.micro)
┌──────────────┐          ┌─────────────────────┐
│  server.py   │──HTTP──→ │  FastAPI + SQLite    │
│  6 MCP tools │          │  mailbox/app.py      │
└──────────────┘          └──────────┬───────────┘
                                     │
              ┌──────────────────────┼──────────────┐
              │                      │              │
           Oppy (masuda)          Jerry (cluster)
           mailbox_mcp.py         mailbox_mcp.py
```

## Tools

| Tool | Description |
|------|-------------|
| `spawn_terminal(command?, app?)` | Open a Terminal.app/iTerm2 window |
| `connect_to_brother(name)` | SSH to Oppy or Jerry with Claude Code |
| `send_message(recipients, body, subject?)` | Send a message to brothers |
| `check_mailbox(unread_only?, limit?)` | List received messages |
| `read_message(message_id)` | Read a message (auto-marks as read) |
| `unread_count()` | Quick unread check |

## Setup

See [GUIDE.md](GUIDE.md) for full setup and deployment documentation.

**New brother?** See [BROTHER_MAILBOX_SETUP.md](BROTHER_MAILBOX_SETUP.md) for self-setup instructions.

## Testing

```bash
conda activate terminal-spawner
python -m pytest test_terminal_spawner.py test_mailbox.py -v
```

86 tests covering terminal spawning, mailbox server, HTTP client, MCP tools, and integration.

## Project Structure

```
server.py              MCP server for Doot (terminal + mailbox tools)
terminal.py            AppleScript generation + execution
brothers.py            Brother SSH configurations
mailbox_client.py      HTTP client for the mailbox API
mailbox_mcp.py         MCP server for remote brothers (mailbox only)
mailbox/               FastAPI server (deployed to EC2)
deploy/                EC2 provisioning scripts
```
