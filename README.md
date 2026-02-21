# Clade

Infrastructure for networks of [Claude Code](https://claude.com/claude-code) instances that communicate, collaborate, and delegate work to each other autonomously. Designed by [Ian Dunn](https://github.com/dunni3).

## What Is a Clade?

A **clade** is a group of Claude Code instances — called **brothers** — that share a communication hub and can delegate tasks to each other. One brother acts as a **coordinator** (the human's direct interface), while **worker** brothers run on remote machines. An optional **conductor** orchestrates multi-step workflows by delegating tasks to workers and reviewing results automatically.

Clade handles the hard parts: identity, authentication, messaging, task tracking, and the plumbing to spawn Claude Code sessions on remote machines over SSH or HTTP.

## Core Concepts

### The Hearth

A shared FastAPI + SQLite server that all brothers connect to. It stores messages, tasks, morsels, and member registry. Every brother authenticates with their own API key. Includes a React web UI for browsing everything from a browser.

### Task Trees

Tasks form **trees** that grow organically. When any task completes, the conductor wakes up, reviews the result, and can delegate follow-up tasks as **children** of the completed task. This builds a tree of work without any upfront planning — the structure emerges from the work itself.

```
Root Task: "Evaluate model performance"
├── Child 1: "Run docking benchmarks" (completed)
│   ├── Grandchild: "Analyze docking scores" (completed)
│   └── Grandchild: "Generate summary plots" (in_progress)
└── Child 2: "Run binding affinity predictions" (failed → retried)
    └── Retry: "Run binding affinity predictions (retry)" (completed)
```

Trees are the primary structural unit. Every task is part of a tree (standalone tasks are single-node trees). The web UI visualizes trees as interactive directed graphs with status-colored nodes.

**Guardrails:** Max tree depth of 5, max 2 retries for failed tasks, worker load checks before delegating.

### Morsels

A structured observation log. Any brother can deposit a **morsel** — a tagged note linked to tasks, workflows, or other brothers. Unlike messages (directed communication), morsels are broadcast observations useful for audit trails and cross-session context.

### Embers

Lightweight HTTP servers running on worker machines. They accept task execution requests and launch Claude Code sessions in tmux. This enables the conductor to orchestrate work without SSH access — just HTTP calls over a Tailscale mesh VPN.

Workers can run **multiple concurrent tasks** (called "aspens") on a single Ember.

### Brothers and Roles

| Role | MCP Server | Description |
|------|-----------|-------------|
| **Coordinator** | `clade-personal` | Human's direct interface. Mailbox, SSH delegation, Ember health. |
| **Worker** | `clade-worker` | Remote Claude Code instance. Mailbox, task updates, local Ember. |
| **Conductor** | `clade-conductor` | Automated orchestrator. Delegates tasks, builds trees, deposits morsels. |

## Architecture

```
                 ┌─────────────────────────────────────┐
                 │           The Hearth (EC2)           │
                 │      FastAPI + SQLite + Web UI       │
                 │                                      │
                 │  Messages ── Tasks ── Trees ── Morsels│
                 └───┬─────────┬──────────┬─────────┬──┘
                     │         │          │         │
          ┌──────────┘         │          │         └──────────┐
          │                    │          │                     │
  Coordinator            Conductor    Human (browser)      Workers
  clade-personal         clade-conductor  Web UI          clade-worker
  Mailbox + Tasks        Trees + Delegation                Mailbox + Tasks
  + SSH Delegation       Event-driven ticks
          │                    │
          │ SSH                │ HTTP (Ember)
          │                    │
          ▼                    ▼
   ┌─────────────┐     ┌─────────────┐
   │   Workers    │     │   Embers    │
   │  (tmux +     │     │  (FastAPI   │
   │   Claude)    │     │   on each   │
   │              │     │   worker)   │
   └─────────────┘     └─────────────┘
```

**Two delegation paths:**
- **SSH (Coordinator → Workers):** Direct SSH + tmux sessions for ad-hoc tasks
- **Ember (Conductor → Workers):** HTTP task execution servers, enabling automated orchestration without SSH

**Connectivity:** Brothers communicate through a [Tailscale](https://tailscale.com/) mesh VPN, bypassing firewalls and NAT. Ember servers bind to Tailscale IPs.

**Event-driven conductor:** The conductor ticks are triggered three ways:
1. **Task events** — any task reaches `completed` or `failed`
2. **Messages** — someone sends a message to the conductor
3. **Timer** — periodic systemd timer (configurable interval)

Each tick spawns a short-lived Claude Code session that reviews what happened and decides what to do next.

## Getting Started

```bash
pip install -e .

# Initialize your clade (interactive wizard)
clade init

# Restart Claude Code to pick up the MCP server, then:
clade add-brother --ember    # Onboard a remote worker with an Ember server
clade setup-conductor        # Deploy the automated conductor
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `clade init` | Interactive setup wizard (name, personality, server config, API keys, MCP registration) |
| `clade add-brother` | Onboard a remote worker (`--ember` to deploy Ember server) |
| `clade setup-ember` | Deploy an Ember server on an existing brother |
| `clade setup-conductor` | Deploy the Conductor on the Hearth server |
| `clade deploy {hearth,frontend,conductor,ember,all}` | Deploy code updates |
| `clade status` | Health overview (server, SSH, keys) |
| `clade doctor` | Full diagnostics for the entire setup |

### Onboarding Flow

```
clade init → clade add-brother --ember → clade setup-conductor
```

`init` creates the config, API keys, and MCP registration. `add-brother --ember` onboards a remote brother and deploys an Ember server. `setup-conductor` deploys the automated conductor, wired to all brothers with Ember servers.

## Tools

### Coordinator (clade-personal)

| Tool | Description |
|------|-------------|
| `list_brothers()` | List available brother instances |
| `send_message(recipients, body, subject?)` | Send a message to brothers |
| `check_mailbox(unread_only?, limit?)` | List received messages |
| `read_message(message_id)` | Read a message (marks as read) |
| `browse_feed(limit?, offset?, sender?, recipient?, query?)` | Browse all messages |
| `unread_count()` | Quick unread check |
| `initiate_ssh_task(brother, prompt, subject?, max_turns?, parent_task_id?)` | Delegate a task via SSH |
| `list_tasks(assignee?, status?, limit?)` | Browse task list |
| `get_task(task_id)` | Get task details |
| `update_task(task_id, status?, output?)` | Update task status |
| `kill_task(task_id)` | Kill a running task |
| `deposit_morsel(body, tags?, task_id?, brother?)` | Deposit an observation/note |
| `list_morsels(creator?, tag?, task_id?, limit?)` | List morsels with filters |
| `list_trees(limit?)` | List task trees with status summaries |
| `get_tree(root_task_id)` | Get full task tree hierarchy |
| `check_ember_health(url?)` | Check an Ember server's health |
| `list_ember_tasks()` | List active tasks on configured Ember |

### Conductor (clade-conductor)

| Tool | Description |
|------|-------------|
| `delegate_task(worker, prompt, subject?, max_turns?, parent_task_id?)` | Delegate a task to a worker via Ember (auto-links parent from trigger context) |
| `check_worker_health(worker?)` | Check one or all worker Ember servers |
| `list_worker_tasks(worker?)` | List active tasks on worker Embers |
| `deposit_morsel(body, tags?, task_id?, brother?)` | Deposit an observation/note |
| `list_morsels(creator?, tag?, task_id?, limit?)` | List morsels with filters |
| `list_trees(limit?)` | List task trees with status summaries |
| `get_tree(root_task_id)` | Get full task tree hierarchy |
| Mailbox tools | send, check, read, browse, unread |
| Task tools | list, get, update |

### Workers (clade-worker)

| Tool | Description |
|------|-------------|
| `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` | Mailbox communication |
| `list_tasks`, `get_task`, `update_task`, `kill_task` | Task visibility, status updates, and kill |
| `deposit_morsel(body, tags?, task_id?, brother?)` | Deposit an observation/note |
| `list_morsels(creator?, tag?, task_id?, limit?)` | List morsels with filters |
| `list_trees(limit?)`, `get_tree(root_task_id)` | Task tree visibility |
| `check_ember_health(url?)`, `list_ember_tasks()` | Local Ember health |

## Project Structure

```
clade/
├── src/clade/                    # Main package
│   ├── core/                     # Config, brother definitions, types
│   ├── cli/                      # CLI commands (init, add-brother, deploy, setup-*, status, doctor)
│   ├── communication/            # Hearth HTTP client
│   ├── tasks/                    # SSH task delegation
│   ├── worker/                   # Ember server + local task runner
│   │   ├── ember.py              # FastAPI Ember server
│   │   ├── runner.py             # Local tmux task launcher
│   │   ├── auth.py               # Bearer token auth
│   │   └── client.py             # EmberClient (httpx)
│   ├── utils/                    # Shared utilities
│   └── mcp/                      # MCP servers and tool definitions
│       ├── server_full.py        # Coordinator server
│       ├── server_lite.py        # Worker server
│       ├── server_conductor.py   # Conductor server
│       └── tools/                # Tool implementations
├── hearth/                       # Hearth API server (deployed to EC2)
├── frontend/                     # Web UI (Vite + React + TypeScript + Tailwind)
├── tests/                        # Unit + integration tests
├── docker/                       # Docker Compose E2E test environment
├── deploy/                       # Deployment scripts and systemd units
└── pyproject.toml                # Package config (5 entry points)
```

**Five entry points** (defined in `pyproject.toml`):
- `clade` — CLI for setup and management
- `clade-personal` — Coordinator MCP server
- `clade-worker` — Worker MCP server
- `clade-ember` — Ember HTTP server (standalone FastAPI, not MCP)
- `clade-conductor` — Conductor MCP server

## Deployment

```bash
clade deploy all                   # Deploy everything
clade deploy hearth                # Hearth server code + deps + restart
clade deploy frontend              # Build + deploy React SPA
clade deploy frontend --skip-build # Deploy pre-built dist/
clade deploy conductor             # Update Conductor
clade deploy ember <name>          # Update clade package on a brother + restart Ember
```

All subcommands use **tar-pipe-SSH** for file transfer (no git dependency on remote hosts), read SSH config from `clade.yaml`, and are non-interactive. `deploy all` continues on failure and prints a summary.

**Initial setup vs updates:**
- `clade setup-ember` / `clade setup-conductor` — first-time setup (detect binaries, generate service files, register keys)
- `clade deploy ember` / `clade deploy conductor` — subsequent code updates and restarts

## Testing

```bash
pip install -e .
python -m pytest tests/ -q
```

A Docker Compose environment in `docker/` provides full E2E testing with coordinator, worker, hearth, and frontend containers. See `docs/docker-testing.md`.

## License

MIT
