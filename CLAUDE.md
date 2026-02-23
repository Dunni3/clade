# The Clade

Infrastructure for networks of Claude Code instances — inter-agent communication, task delegation, and orchestration. Designed by [Ian Dunn](https://github.com/dunni3).

## Project Structure

```
clade/
├── src/clade/                     # Main package (single source of truth)
│   ├── core/                      # Config (brothers, types), YAML loader
│   │   ├── config.py              # load_config(), FALLBACK_CONFIG with brother defs
│   │   ├── brothers.py            # BROTHERS dict (host, working_dir, description)
│   │   └── types.py               # Type definitions
│   ├── cli/                       # CLI commands (`clade` entry point)
│   │   ├── main.py                # Click group + --config-dir, wires up subcommands
│   │   ├── init_cmd.py            # `clade init` — interactive setup wizard + identity writing
│   │   ├── add_brother.py         # `clade add-brother` — SSH test, deploy, key gen, MCP reg, identity
│   │   ├── deploy_cmd.py          # `clade deploy` — deploy group (hearth, frontend, conductor, ember, all)
│   │   ├── deploy_utils.py        # Shared deploy helpers (tar-pipe-SSH, config loading, package deploy)
│   │   ├── status_cmd.py          # `clade status` — health overview
│   │   ├── doctor.py              # `clade doctor` — full diagnostics (incl. identity checks)
│   │   ├── identity.py            # CLAUDE.md identity section generation + upsert
│   │   ├── clade_config.py        # CladeConfig / BrotherEntry dataclasses + YAML persistence
│   │   ├── keys.py                # API key generation + keys.json management
│   │   ├── ssh_utils.py           # test_ssh(), run_remote(), check_remote_prereqs(), deploy_clade_remote()
│   │   ├── mcp_utils.py           # ~/.claude.json read/write/register (local + remote)
│   │   ├── naming.py              # Scientist name pool for brother suggestions
│   │   ├── ember_setup.py         # Ember server detection, deployment, health check
│   │   ├── setup_ember_cmd.py     # `clade setup-ember` — deploy Ember on existing brother
│   │   ├── conductor_setup.py     # Conductor deployment logic
│   │   └── setup_conductor_cmd.py # `clade setup-conductor` — deploy Conductor on Hearth server
│   ├── communication/             # Hearth HTTP client
│   │   └── mailbox_client.py      # MailboxClient (messages + tasks + morsels + trees + ember registry API)
│   ├── tasks/                     # SSH task delegation
│   │   └── ssh_task.py            # build_remote_script, wrap_prompt, initiate_task
│   ├── templates/                 # Jinja2 shell script templates
│   │   ├── local_runner.sh.j2     # Ember runner (worktree isolation + claude launch)
│   │   ├── remote_wrapper.sh.j2   # SSH wrapper (b64 decode + tmux launch)
│   │   ├── remote_inner_runner.sh.j2 # Inner runner (nested in wrapper heredoc)
│   │   └── _failure_trap.sh.j2    # Shared trap: auto-PATCH task to failed on exit
│   ├── worker/                    # Ember server (HTTP-based task execution on workers)
│   │   ├── auth.py                # Bearer token auth (reuses HEARTH_API_KEY)
│   │   ├── runner.py              # Local tmux launcher (Jinja2 templates, git worktree isolation)
│   │   ├── ember.py               # FastAPI Ember server (endpoints + in-memory state)
│   │   └── client.py              # EmberClient (httpx client for Ember API)
│   ├── utils/                     # Shared utilities
│   │   └── timestamp.py           # format_timestamp (timezone-aware, human-friendly)
│   ├── mcp/                       # MCP server definitions
│   │   ├── server_full.py         # Personal/Coordinator server (mailbox + tasks + ember)
│   │   ├── server_lite.py         # Worker Brother server (mailbox + tasks + ember only)
│   │   ├── server_conductor.py    # Conductor server (mailbox + trees + delegation)
│   │   └── tools/
│   │       ├── brother_tools.py   # list_brothers
│   │       ├── kanban_tools.py    # create_card/list_board/get_card/move_card/update_card/archive_card
│   │       ├── mailbox_tools.py   # send/check/read/browse/unread + task list/get/update/kill + deposit_morsel/list_morsels/list_trees/get_tree
│   │       ├── task_tools.py      # initiate_ssh_task (coordinator only)
│   │       ├── delegation_tools.py # initiate_ember_task (coordinator + worker)
│   │       ├── ember_tools.py     # check_ember_health, list_ember_tasks
│   │       └── conductor_tools.py # delegate_task, check_worker_health, list_worker_tasks
│   ├── skills/                    # Bundled skills (SKILL.md format)
│   │   └── implement-card/        # Card implementation + review delegation
│   └── web/                       # Web app backend (unused currently)
├── hearth/                        # Hearth API server (FastAPI + SQLite, deployed on EC2)
│   ├── app.py                     # FastAPI routes (/api/v1/messages, /api/v1/tasks, etc.)
│   ├── db.py                      # SQLite database (messages, tasks, api_keys, morsels, morsel_tags, morsel_links, embers tables)
│   ├── auth.py                    # API key authentication
│   ├── models.py                  # Pydantic request/response models
│   └── config.py                  # Server configuration
├── tests/                         # All tests
│   ├── unit/                      # Fast, no network (config, client, ssh, cli, timestamp)
│   └── integration/               # MCP tool + Hearth server integration tests
├── frontend/                      # Hearth web UI (Vite + React + TypeScript + Tailwind v4)
├── docker/                        # Docker Compose test environment
│   ├── Dockerfile.test            # Personal image — clade CLI, SSH client
│   ├── Dockerfile.test.worker     # Worker image — sshd + Ember server
│   ├── Dockerfile.test.hearth     # Hearth image — FastAPI + conductor config
│   ├── Dockerfile.test.frontend   # Frontend image — Vite dev server
│   ├── docker-compose.test.yml    # Four-service test environment
│   ├── entrypoint-worker.sh       # Worker entrypoint — starts sshd + Ember
│   └── test-conductor-workers.yaml # Static worker registry for test conductor
├── scripts/                       # Convenience scripts
│   └── test-compose.sh            # Docker test env launcher (keygen + build + attach)
├── deploy/                        # Deployment and infrastructure scripts
│   ├── setup.sh                   # EC2 server provisioning
│   ├── ec2.sh                     # EC2 instance management (start/stop/status/ssh)
│   ├── ember.service              # systemd unit for Ember server on masuda
│   ├── conductor-tick.sh          # Conductor tick script (runs periodic check-in)
│   ├── conductor-tick.md          # Conductor tick prompt (instructions for each tick)
│   ├── conductor-tick.service     # systemd oneshot service for conductor tick
│   ├── conductor-tick.timer       # systemd timer (every 15 min)
│   ├── conductor-workers.yaml     # Example worker registry for the conductor
│   ├── conductor.env.example      # Example conductor env file
│   ├── cluster-tailscale-setup.sh # One-time Tailscale bootstrap for SLURM clusters
│   ├── cluster-tailscale-job.sh   # SLURM job that runs Tailscale (sbatch script)
│   └── cluster-tailscale-start.sh # Submit/stop the Tailscale SLURM job
├── research_notes/                # Development logs and research (gitignored)
├── docs/                          # Documentation
│   └── docker-testing.md          # Full Docker Compose test environment docs
└── HEARTH_SETUP.md                # Self-setup guide for brothers
```

**Five entry points** (defined in `pyproject.toml`):
- `clade` — CLI for setup and management (`cli/main.py`)
- `clade-personal` — Full MCP server: mailbox + task delegation + ember + brother listing
- `clade-worker` — Lite MCP server: mailbox communication + task visibility/updates + ember
- `clade-ember` — Ember server: HTTP listener for task execution on worker machines
- `clade-conductor` — Conductor MCP server: mailbox + trees + worker delegation

## CLI Commands

The `clade` CLI handles onboarding, deployment, and diagnostics:

| Command | Description |
|---------|-------------|
| `clade init` | Interactive wizard: name clade, name personal brother, personality, server config, API key gen + registration (`--server-key`), MCP, identity writing |
| `clade add-brother` | SSH test, prereq check, remote deploy, API key gen + Hearth registration, MCP registration, remote identity writing. `--ember` flag adds Ember setup. |
| `clade deploy hearth` | Deploy Hearth server code via tar pipe, install deps, restart service, health check |
| `clade deploy frontend [--skip-build]` | Build frontend (npm), deploy to `/var/www/hearth/` via staging, verify |
| `clade deploy conductor [--personality] [--no-identity]` | Deploy Conductor (delegates to existing `deploy_conductor()` with `yes=True`) |
| `clade deploy ember <name>` | Deploy clade package to a brother, restart Ember service, health check |
| `clade deploy all [--skip-build]` | Run hearth → frontend → conductor → ember (all brothers) in sequence; continues on failure, prints summary |
| `clade setup-ember` | **Initial** Ember setup on a brother: detect binary/user/Tailscale IP, template systemd service, start + health check. Use `deploy ember` for subsequent updates. |
| `clade setup-conductor` | **Initial** Conductor setup on the Hearth server: config files, systemd timer, identity. Idempotent — re-run to update workers config. Use `deploy conductor` for subsequent updates. |
| `clade status` | Health overview: server ping, SSH to each brother, key status |
| `clade doctor` | Full diagnostic: config, keys, MCP, identity, server, per-brother SSH + package + MCP + identity + Hearth + Ember health |

**Global option:** `--config-dir PATH` overrides where `clade.yaml`, `keys.json`, and local `CLAUDE.md` are written. Useful for isolated testing. Does not affect remote paths.

Config lives in `~/.config/clade/clade.yaml` (created by `init`, updated by `add-brother`). API keys in `~/.config/clade/keys.json` (chmod 600). `core/config.py` detects `clade.yaml` (has `clade:` top-level key) with highest priority and converts it to `TerminalSpawnerConfig` so MCP servers work unchanged.

## Identity System

Each brother gets an identity section in their `~/.claude/CLAUDE.md`, telling them who they are, what tools they have, and who their family is.

**Key file:** `src/clade/cli/identity.py`

- **HTML comment markers:** `<!-- CLADE_IDENTITY_START -->` / `<!-- CLADE_IDENTITY_END -->` delimit the identity section
- **Non-destructive upsert:** If markers exist, replace between them. If no markers, append. Empty file creates fresh.
- **Three identity flavors:**
  - `generate_personal_identity()` — for the coordinator (lists all personal server tools)
  - `generate_worker_identity()` — for worker brothers (lists worker server tools + family list)
  - `generate_conductor_identity()` — for the conductor (lists conductor tools + workers + brothers)
- **Shared concepts:** `_shared_concepts()` generates a "Key Concepts" section (Task Trees, Morsels, Board Cards) included in all three flavors. Each flavor adds role-specific guidance (Delegation Best Practices, Conductor Rules, Worker Guidelines).
- **Personality:** Optional free-text description stored in `clade.yaml`, included in the identity section
- **Local writing:** `write_identity_local()` reads/upserts/writes `~/.claude/CLAUDE.md`
- **Remote writing:** `write_identity_remote()` base64-encodes the identity, SSHes to remote, runs a Python upsert script
- **`--no-identity`:** Both `init` and `add-brother` accept this flag to skip identity writing
- **Doctor checks:** WARN-level checks for local and remote identity presence (not failures)

## MCP Tools

### Coordinator tools (clade-personal)
- `list_brothers()` — List available brother instances
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `initiate_ember_task(brother, prompt, subject?, parent_task_id?, working_dir?, max_turns?, card_id?, on_complete?, blocked_by_task_id?)` — **Primary delegation path.** Delegate a task to a brother via their Ember server. Supports deferred execution via `blocked_by_task_id`.
- `initiate_ssh_task(brother, prompt, subject?, working_dir?, max_turns?, auto_pull?, parent_task_id?, on_complete?, card_id?)` — Delegate a task via SSH + tmux (legacy path)
- `list_tasks(assignee?, status?, limit?)`, `get_task(task_id)`, `update_task(task_id, ...)` — Task management
- `kill_task(task_id)` — Kill a running task (terminates tmux session on Ember, marks as `killed`)
- `retry_task(task_id)` — Retry a failed task (creates child task with same prompt, sends to Ember)
- `deposit_morsel(body, tags?, task_id?, brother?, card_id?)` — Deposit an observation/note
- `list_morsels(creator?, tag?, task_id?, card_id?, limit?)` — List morsels with filters
- `list_trees(limit?)` — List task trees with status summaries
- `get_tree(root_task_id)` — Get full task tree hierarchy
- `check_ember_health(brother?, url?)` — Check Ember health (by brother name, URL, or all brothers in registry)
- `list_ember_tasks(brother?)` — List active tasks on Ember(s) (by brother name or all)
- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board

### Conductor tools (clade-conductor)
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task` — Task visibility and status updates
- `delegate_task(brother, prompt, subject?, parent_task_id?, working_dir?, max_turns?, card_id?, on_complete?, blocked_by_task_id?)` — Delegate a task to a worker via Ember. Auto-reads `TRIGGER_TASK_ID` from env for parent linking when `parent_task_id` is not explicitly set. Supports deferred execution via `blocked_by_task_id`.
- `check_worker_health(worker?)` — Check one or all worker Ember servers
- `list_worker_tasks(worker?)` — List active tasks on worker Embers
- `deposit_morsel(body, tags?, task_id?, brother?, card_id?)` — Deposit an observation/note
- `list_morsels(creator?, tag?, task_id?, card_id?, limit?)` — List morsels with filters
- `list_trees(limit?)` — List task trees with status summaries
- `get_tree(root_task_id)` — Get full task tree hierarchy
- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board

### Worker tools (clade-worker)
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task`, `kill_task`, `retry_task` — Task visibility, status updates, kill, and retry
- `initiate_ember_task(brother, prompt, subject?, parent_task_id?, working_dir?, max_turns?, card_id?, on_complete?, blocked_by_task_id?)` — Delegate tasks to sibling brothers via their Embers
- `deposit_morsel(body, tags?, task_id?, brother?, card_id?)` — Deposit an observation/note
- `list_morsels(creator?, tag?, task_id?, card_id?, limit?)` — List morsels with filters
- `list_trees(limit?)` — List task trees with status summaries
- `get_tree(root_task_id)` — Get full task tree hierarchy
- `check_ember_health(brother?, url?)` — Check Ember health (local or by brother name)
- `list_ember_tasks(brother?)` — List active tasks on Ember(s)
- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board

## Task Delegation System

Two delegation paths exist. **Ember (HTTP) is the primary path**; SSH is legacy.

### Ember Delegation (primary)

1. Coordinator/worker calls `initiate_ember_task(brother, prompt, ...)`
2. Task is created in the Hearth database (status: `pending`). If `parent_task_id` is set, the task is linked as a child.
3. If `blocked_by_task_id` is set and the blocker hasn't completed, the task stays `pending` — auto-delegated server-side when the blocker completes (see Deferred Dependencies below).
4. Otherwise, the task is sent to the brother's Ember server via HTTP, which launches a tmux session running `claude -p "<prompt>" --dangerously-skip-permissions`.

### SSH Delegation (legacy)

`initiate_ssh_task()` SSHes to the brother's host and launches a detached tmux session directly. Same lifecycle, but requires SSH access.

### Runner Script Templates (Jinja2)

Runner scripts use **Jinja2 two-phase rendering** (replaced the old heredoc string-building):

- `local_runner.sh.j2` — Ember runner: env setup → git worktree isolation → claude launch → cleanup
- `remote_wrapper.sh.j2` — SSH wrapper: base64 prompt decode → write inner runner to temp → tmux launch
- `remote_inner_runner.sh.j2` — Inner runner (nested in wrapper's heredoc): env exports → cd → claude launch
- `_failure_trap.sh.j2` — Shared trap: on non-zero exit, auto-PATCHes task status to `failed` via Hearth API with last 5 log lines. Distinguishes pre-Claude failures from post-Claude failures via `_CLAUDE_STARTED` flag.

Templates live in `src/clade/templates/`.

### Git Worktree Isolation

The Ember runner (local_runner.sh.j2) creates a git worktree for each task:
- **Path:** `~/.clade-worktrees/<session_name>`
- **Branch:** `clade/<session_name>` (falls back to detached HEAD)
- **Cleanup:** On exit, if the worktree has no staged/unstaged changes, it's automatically removed along with the branch. Dirty worktrees are preserved.

### Task Fields

- **`on_complete`**: Follow-up instructions the conductor reads as a "primary directive" when the task completes. Copied on `retry_task`. Used by the `implement-card` skill to chain implementation → review.
- **`card_id`**: Links the task to a kanban card. Creates a formal link so the card tracks which tasks work on it.

### Deferred Dependencies (`blocked_by_task_id`)

Tasks can declare a dependency on another task. The Hearth handles this server-side:
- On task creation, if `blocked_by_task_id` is set and the blocker is still active, the task stays `pending`.
- If the blocker has already completed, `blocked_by_task_id` is auto-cleared at insert time.
- When a task **completes**, `_unblock_and_delegate()` finds blocked tasks and auto-delegates them to their assignee's Ember.
- When a task **fails**, `_cascade_failure()` recursively fails all downstream blocked tasks.
- `parent_task_id` is auto-defaulted to `blocked_by_task_id` for tree linking.

### Retry

`POST /api/v1/tasks/{task_id}/retry` — creates a child task with the same prompt, delegates to the assignee's Ember, copies `on_complete`. MCP tool: `retry_task(task_id)` (available on all servers). Does NOT trigger conductor ticks.

### Task Lifecycle

`pending` → `launched` → `in_progress` → `completed` / `failed` / `killed`

**Kill flow:** Frontend/MCP → Hearth `POST /tasks/{id}/kill` → Ember `POST /tasks/{task_id}/kill` → `tmux kill-session` → status set to `killed`. Killed tasks do NOT trigger conductor ticks.

**Card auto-sync:** When a task moves to `in_progress`, linked kanban cards in `backlog`/`todo` are auto-moved to `in_progress` and their assignee is updated.

**Runner logging:** Runner scripts log to `/tmp/claude_runner_<session_name>.log`. Logs auto-delete on success, preserved on failure.

**Key files:** `src/clade/tasks/ssh_task.py`, `src/clade/worker/runner.py`, `src/clade/mcp/tools/delegation_tools.py`

## Task Trees

Tasks form parent-child hierarchies that grow organically. When any task completes or fails, the conductor is triggered, reviews the result, and can delegate follow-up tasks as children. This creates a tree of work without upfront planning.

**DB schema:** `parent_task_id` and `root_task_id` columns on the tasks table. Every standalone task has `root_task_id = self.id` (single-node tree). When a child is created, it inherits `root_task_id` from its parent.

**API:** `GET /api/v1/trees` returns root tasks with per-status child counts. `GET /api/v1/trees/{root_id}` returns the full recursive tree. `POST /api/v1/tasks` accepts optional `parent_task_id`; `root_task_id` is auto-computed.

**Frontend:** TreeListPage shows all trees with status breakdown pills. TreeDetailPage renders an interactive React Flow graph (dagre layout) with status-colored nodes, click-to-inspect side panel, animated edges for in-progress tasks. Dependencies: `@xyflow/react`, `dagre`.

**Auto-parent linking:** The tick prompt instructs the conductor to always pass `parent_task_id=TRIGGER_TASK_ID` explicitly when delegating follow-up tasks. The `delegate_task()` tool also reads `TRIGGER_TASK_ID` from env as a safety net when `parent_task_id` is not provided.

## Morsels

A structured observation repository. Any brother can deposit a **morsel** — a tagged note linked to tasks or brothers. Unlike messages (directed communication), morsels are broadcast observations for audit trails and cross-session context.

**DB schema:** Three tables: `morsels` (id, creator, body, created_at), `morsel_tags` (morsel_id, tag), `morsel_links` (morsel_id, object_type, object_id).

**API:** `POST /api/v1/morsels` to create, `GET /api/v1/morsels` with filtering by creator, tag, linked object. `GET /api/v1/morsels/{id}` for detail.

**Frontend:** MorselFeedPage with creator/tag filters. Reusable MorselPanel component shown contextually on TaskDetailPage and TreeDetailPage.

**Conductor integration:** The conductor deposits a morsel at the end of every tick (tagged `conductor-tick`), summarizing observations and actions.

## Kanban Board

A shared kanban board for tracking development work. All brothers can create, view, and update cards. Only creators and admins can delete.

**DB schema:** `kanban_cards` (id, title, description, col, priority, assignee, creator, created_at, updated_at) + `kanban_card_labels` (card_id, label) + `kanban_card_links` (card_id, object_type, object_id).

**Columns:** `backlog`, `todo`, `in_progress`, `done`, `archived`. Archived excluded by default. Sorted by priority desc, then recency.

**Priorities:** `low`, `normal`, `high`, `urgent`.

**API** (under `/api/v1/kanban/cards`):
| Method | Path | Status | Notes |
|--------|------|--------|-------|
| POST | `/kanban/cards` | 201 | Validate col/priority |
| GET | `/kanban/cards` | 200 | Filters: col, assignee, creator, priority, label, include_archived |
| GET | `/kanban/cards/{id}` | 200 | 404 if missing |
| PATCH | `/kanban/cards/{id}` | 200 | Any auth'd user can update |
| DELETE | `/kanban/cards/{id}` | 204 | Creator or admin only |

**MCP tools** (registered on all 3 servers — personal, worker, conductor):
- `create_card(title, description?, col?, priority?, assignee?, labels?, links?)` — create a card (links: list of `{object_type, object_id}`)
- `list_board(col?, assignee?, label?, include_archived?)` — show cards grouped by column
- `get_card(card_id)` — full card details (includes linked objects)
- `move_card(card_id, col)` — move to a column
- `update_card(card_id, title?, description?, priority?, assignee?, labels?, links?)` — edit fields
- `archive_card(card_id)` — move to archived

**Frontend:** `/board` route, KanbanPage with 4-column horizontal layout, move buttons, create form, detail/edit modal, filters.

## Ember Server (HTTP-based Task Execution)

An **Ember** is a lightweight HTTP server running on a worker brother's machine that accepts task execution requests. It replaces SSH-based delegation with HTTP triggers, enabling the Conductor to orchestrate tasks without SSH access.

**Architecture:** The Ember is a separate process from the `clade-worker` MCP server. The MCP server's lifecycle is tied to a Claude Code session (stdio transport). The Ember runs 24/7, waiting for incoming task requests even when no Claude session is active.

**Key files:**
- `src/clade/worker/ember.py` — FastAPI app with endpoints
- `src/clade/worker/runner.py` — Local tmux launcher (renders `local_runner.sh.j2`, git worktree isolation)
- `src/clade/worker/auth.py` — Bearer token auth
- `src/clade/worker/client.py` — `EmberClient` for calling Ember APIs

**Endpoints:**
| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | No | Liveness check (brother name, active tasks, uptime) |
| `POST /tasks/execute` | Yes (202) | Launch a Claude Code tmux session (supports concurrent aspens). |
| `POST /tasks/{task_id}/kill` | Yes | Kill a running task's tmux session |
| `GET /tasks/active` | Yes | List of active aspens + orphaned tmux sessions |

**Authentication:** Embers reuse the brother's Hearth API key (`HEARTH_API_KEY` env var) — no separate Ember key needed. The coordinator authenticates to a remote Ember using the brother's Hearth key (from `keys.json`). Workers authenticate to their local Ember using their own Hearth key.

**Env vars** (for the Ember server process):
| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `EMBER_PORT` | No | `8100` | HTTP port |
| `EMBER_HOST` | No | `0.0.0.0` | Bind address |
| `EMBER_BROTHER_NAME` | No | `oppy` | Self-identification |
| `EMBER_WORKING_DIR` | No | — | Default working dir for tasks |
| `HEARTH_API_KEY` | Yes | — | Auth token (validated for incoming requests, also passed to spawned Claude sessions) |
| `HEARTH_URL` | No | — | Passed to spawned Claude sessions |
| `HEARTH_NAME` | No | — | Passed to spawned Claude sessions |

**MCP env vars** (for Ember *client* in MCP servers):
- Workers: `EMBER_URL=http://localhost:8100` (local Ember, uses existing `HEARTH_API_KEY`)
- Coordinator: `EMBER_URL=http://<brother-tailscale-ip>:8100` + `EMBER_API_KEY=<brother's Hearth key>`

**In-memory state:** `AspenRegistry` tracks all running aspens (concurrent Claude Code sessions). No DB — the Hearth is source of truth. `reap()` sweeps dead tmux sessions automatically.

**Deployment:** Automated via `clade setup-ember <name>` or `clade add-brother --ember`. The CLI detects the remote user, `clade-ember` binary path, clade package directory, and Tailscale IP, then templates and deploys a systemd service. Falls back to printing manual instructions if sudo is unavailable. After a successful health check, the Ember URL is **auto-registered** with the Hearth DB via `PUT /api/v1/embers/{name}` (best-effort — failure is non-fatal). Reference service file: `deploy/ember.service`. Config fields `ember_host` and `ember_port` are stored in `BrotherEntry` in `clade.yaml`.

## Conductor — Workflow Orchestration

The **Conductor** is a periodic process that orchestrates multi-step workflows by delegating tasks to worker brothers via their Ember servers. It builds **task trees** organically — when a task completes, the conductor reviews the result and delegates follow-up tasks as children. It runs on the same host as the Hearth.

**Architecture:** Ticks are triggered three ways: (1) a systemd timer (configurable interval), (2) **task-driven** — the Hearth fires a tick when **any** task reaches a terminal state (`completed`/`failed`), passing the task ID to the tick command, and (3) **message-driven** — the Hearth fires a tick when a message is sent to the conductor (not from itself), passing `--message <id>` to the tick command. Each tick spawns a Claude Code session with the `clade-conductor` MCP server. The tick prompt (`conductor-tick.md`) has three paths:
- **Event-driven** (`TRIGGER_TASK_ID` set): Fetch the triggering task, assess follow-up needs. For failures, prefer `retry_task()`. For completions needing follow-up, delegate children with explicit `parent_task_id=TRIGGER_TASK_ID`. Deposit morsel, check mailbox.
- **Message-driven** (`TRIGGER_MESSAGE_ID` set): Read the triggering message, respond if appropriate, act on requests (delegate task), deposit morsel, check other unread messages
- **Periodic** (timer, no trigger): Check mailbox, scan for stuck tasks (launched >10 min — re-delegate as child, mark original failed), check worker health, deposit morsel

**Auto-parent linking:** The tick prompt instructs the conductor to always pass `parent_task_id=TRIGGER_TASK_ID` explicitly. The `delegate_task()` tool also reads `TRIGGER_TASK_ID` from env as a safety net. Explicit `parent_task_id` overrides the env var.

**Guardrails:** Max tree depth 5, max 2 retries (prefer `retry_task()` for failed tasks), check worker aspen load before delegating. The conductor deposits a morsel at the end of every tick summarizing observations and actions.

**Key files:**
- `src/clade/mcp/server_conductor.py` — MCP server (mailbox + trees + delegation tools)
- `src/clade/mcp/tools/conductor_tools.py` — Worker delegation tools
- `src/clade/cli/conductor_setup.py` — Deployment logic
- `src/clade/cli/setup_conductor_cmd.py` — `clade setup-conductor` CLI command
- `deploy/conductor-tick.sh` — Tick runner script
- `deploy/conductor-tick.md` — Tick prompt

**MCP config:** Uses console_scripts entry point path (e.g., `/home/ubuntu/.local/venv/bin/clade-conductor`) instead of `python -m`. All MCP registrations (local + remote) use absolute binary paths.

**Deployment flow:**
```
clade init → clade add-brother --ember → clade setup-conductor
```

The command is separate from `init` because the Conductor needs brother Ember info that only exists after `add-brother --ember`. It's idempotent — re-run to update the workers config when brothers change.

**What `clade setup-conductor` does:**
1. SSHes to the Hearth server (`server.ssh` in clade.yaml)
2. Deploys/updates the clade package
3. Generates the conductor's API key (idempotent) and registers with the Hearth
4. Builds `conductor-workers.yaml` from brothers with `ember_host` set
5. Builds `conductor.env` and `conductor-mcp.json`
6. Writes all config files to `~/.config/clade/` on the remote
7. Copies tick script + prompt to `~/.config/clade/`
8. Deploys systemd service + timer, enables and starts the timer
9. Writes the conductor's identity to remote `~/.claude/CLAUDE.md`

**Remote config layout** (on EC2 at `~/.config/clade/`):
- `conductor-workers.yaml` — Worker registry with Ember URLs and API keys
- `conductor.env` — Hearth connection + workers config path
- `conductor-mcp.json` — MCP config for `claude --mcp-config` during ticks
- `conductor-tick.sh` — Tick runner script
- `conductor-tick.md` — Tick prompt

**Checking status:**
```bash
ssh <server-ssh> systemctl status conductor-tick.timer   # timer status
ssh <server-ssh> sudo journalctl -u conductor-tick -n 50  # recent tick logs
ssh <server-ssh> sudo systemctl start conductor-tick.service  # manual trigger
```

## The Hearth (Communication Hub)

- **API server:** FastAPI + SQLite on EC2 (`44.195.96.130`, HTTPS on 443)
- **Web UI:** React SPA at `https://44.195.96.130` (source in `frontend/`)
  - **Pages:** Inbox, Feed, Tasks, Task Detail, Trees, Tree Detail (React Flow graph), Morsels, Morsel Detail, Board (kanban with project filter), Status, Compose, Settings
  - **Components:** `Linkify` (auto-detects URLs in text), `PeekDrawer` (side panel for quick object inspection on kanban board — supports morsel/task/tree/card/message types)
- **Members:** Each brother, the coordinator, the conductor, and the human each get their own API key
- **Admins:** The human and coordinator can edit/delete any message; others only their own
- **Env vars:** `HEARTH_URL`, `HEARTH_API_KEY`, `HEARTH_NAME` (with `MAILBOX_*` fallback for transition)
- **Dynamic key registration:** API keys can be registered via `POST /api/v1/keys` (any authenticated user). The CLI does this automatically during `clade init --server-key`, `clade add-brother`, and `clade setup-conductor`. Auth checks env-var keys first (fast), then falls back to DB-registered keys.
- **Recipient validation:** `POST /api/v1/messages` validates recipients against registered members (env-var keys + DB keys). Unknown recipients return 422.
- **Health endpoint:** `GET /api/v1/health` — simple liveness check
- **Members API:** `GET /api/v1/members/activity` — per-member stats (messages sent, active/completed/failed tasks, last activity timestamps)
- **Task trees:** Tasks support parent-child relationships via `parent_task_id` and `root_task_id` columns. Trees grow organically as the conductor delegates follow-up tasks. API: `GET /api/v1/trees` (list with status summaries), `GET /api/v1/trees/{root_id}` (full recursive tree). `POST /api/v1/tasks` accepts optional `parent_task_id`; `root_task_id` is auto-computed.
- **Morsels:** Structured observation repository. Any brother can deposit a morsel (text note tagged with keywords and linked to tasks/brothers). Tables: `morsels`, `morsel_tags`, `morsel_links`. API: `POST /api/v1/morsels`, `GET /api/v1/morsels` (filtered by creator/tag/linked object), `GET /api/v1/morsels/{id}`.
- **Ember registry (DB-backed):** Ember URLs stored in `embers` table instead of env var. API: `PUT /api/v1/embers/{name}` (register/update), `GET /api/v1/embers` (list), `DELETE /api/v1/embers/{name}` (admin). `GET /api/v1/embers/status` merges DB entries with `EMBER_URLS` env var (DB wins on conflict). `clade setup-ember` auto-registers after deployment.
- **Task events:** `POST /api/v1/tasks/{task_id}/log` — log events (tool calls, progress updates) against a task. Events stored in `task_events` table and returned with task detail.
- **Kill endpoint:** `POST /api/v1/tasks/{id}/kill` — proxies to the assignee's Ember to terminate the tmux session, then marks the task `killed` in DB. Only creator or admins can kill. Returns 409 for non-active tasks. Does NOT trigger conductor ticks.
- **Retry endpoint:** `POST /api/v1/tasks/{id}/retry` — creates a child task with same prompt, delegates to Ember, copies `on_complete`. Only failed tasks can be retried. Does NOT trigger conductor ticks.
- **Deferred dependencies:** Tasks accept `blocked_by_task_id`. When the blocker completes, `_unblock_and_delegate()` auto-delegates. When the blocker fails, `_cascade_failure()` recursively fails downstream tasks.
- **Card auto-sync:** When a task moves to `in_progress`, linked kanban cards in `backlog`/`todo` auto-move to `in_progress` with updated assignee.
- **Event-driven conductor ticks:** `CONDUCTOR_TICK_CMD` env var. When set, the Hearth fires the conductor tick (fire-and-forget) on: **any** task completion/failure (not kills), messages sent to the conductor (not from itself), Task ID is passed as a positional arg; message ID is passed as `--message <id>`.

## Testing

```bash
# Run all tests (from project root, in clade conda env)
python -m pytest tests/ -q
```

**Important:** When mocking httpx responses in tests, use `MagicMock` (not `AsyncMock`) since `.json()` and `.raise_for_status()` are sync methods.

### Docker Compose Test Environment

A multi-container environment for full end-to-end testing of the CLI onboarding flow, Ember delegation, and Conductor orchestration without real SSH hosts or a deployed Hearth. See `docs/docker-testing.md` for full details.

```bash
bash scripts/test-compose.sh   # keygen + build + start + attach to personal container
```

Four containers: `personal` (coordinator), `worker` (sshd + Ember), `hearth` (FastAPI + conductor config), `frontend` (Vite dev server at `localhost:5173`). Pre-configured test API keys. Claude Code auth via `ANTHROPIC_API_KEY` in `docker/.env` (gitignored).

## Deployment

**Automated deployment** via `clade deploy`:
```bash
clade deploy all              # Deploy everything (hearth + frontend + conductor + ember)
clade deploy hearth            # Just the Hearth server
clade deploy frontend          # Build + deploy frontend
clade deploy frontend --skip-build  # Deploy pre-built dist/
clade deploy conductor         # Update Conductor
clade deploy ember oppy        # Update clade package on a brother + restart Ember
```

All subcommands read SSH config from `clade.yaml` (server.ssh, server.ssh_key, brothers), use **tar-pipe-SSH** for file transfer (no git dependency, no intermediate files), and are non-interactive. `deploy all` continues on failure and prints a summary.

**File transfer strategies:**
- `scp_directory()` — `tar | ssh sudo tar` for root-owned targets (e.g., `/opt/hearth/hearth/`)
- `scp_build_directory()` — `tar | ssh tar` to `/tmp` staging, then `sudo cp + chown` for non-root targets (e.g., `/var/www/hearth/` owned by `www-data`)
- `deploy_clade_package()` — `tar | ssh tar` to `~/.local/share/clade/`, then auto-detect pip and `pip install -e .`

**`deploy_clade_remote()` in `ssh_utils.py`** now delegates to `deploy_clade_package()` from `deploy_utils.py`, so `add-brother` and `setup-conductor` also use the tar-based approach (no git clone/pull).

**Infrastructure:**
- **EC2 host:** `44.195.96.130` (Elastic IP, instance `i-062fa82cdf32d009a`)
- **Management:** `deploy/ec2.sh {start|stop|status|ssh}`
- **Hearth service:** `sudo systemctl restart hearth` on EC2
- **Conductor timer:** `sudo systemctl restart conductor-tick.timer` on EC2

**Initial setup vs updates:**
- `clade setup-ember` / `clade setup-conductor` — first-time setup (detect binaries, generate service files, register keys)
- `clade deploy ember` / `clade deploy conductor` — subsequent code updates and restarts

## Tailscale Mesh VPN

The Clade uses Tailscale for direct brother-to-brother connectivity. To join the mesh:

**If you have root access** (e.g. masuda, EC2, personal machines):
Tailscale is installed system-wide and runs as a service. It's always on — nothing to do.

**If you're on a shared SLURM cluster with no root** (e.g. university HPC):
Tailscale runs in userspace networking mode inside a SLURM job. Scripts in `deploy/` handle this:

1. **One-time setup** (human runs this once, needs an auth key from [Tailscale admin](https://login.tailscale.com/admin/settings/keys)):
   ```bash
   bash ~/projects/clade/deploy/cluster-tailscale-setup.sh --authkey tskey-auth-XXXXX
   ```

2. **Connect to the mesh** (run anytime — submits a 24h SLURM job to `dept_cpu`):
   ```bash
   bash ~/projects/clade/deploy/cluster-tailscale-start.sh
   ```

3. **Disconnect:**
   ```bash
   bash ~/projects/clade/deploy/cluster-tailscale-start.sh --stop
   ```

Brothers on SLURM clusters are **intermittently available** — online only while the job is running. See `docs/cluster-tailscale-setup.md` for full details and troubleshooting.

**Tailscale + Ember:** `clade setup-ember` auto-detects the brother's Tailscale IP and uses it as the `ember_host` in config. This means Ember health checks and future Conductor calls route through the Tailscale mesh, bypassing firewalls. If Tailscale isn't available, it falls back to the SSH hostname.

## Brothers Registry (Runtime)

Coordinator and workers build the brothers registry at runtime from `clade.yaml` + `keys.json` via `load_brothers_registry()` in `clade_config.py`. Each tool invocation re-reads the files — no caching, so edits take effect immediately without restarting Claude Code. Only brothers with `ember_host` set are included. Legacy fallback via `BROTHERS_CONFIG` env var.

## Skills System

Bundled skills live in `src/clade/skills/`. Each skill is a directory containing `SKILL.md` with YAML frontmatter (`name`, `description`, `argument-hint`, `disable-model-invocation`) and markdown instructions.

**Current skills:**
- `implement-card` — Reads a kanban card, delegates an implementation task to a brother via `initiate_ember_task`, then creates a blocked review task that auto-runs when implementation completes. Arguments: card_id (required), brother (default "oppy"), working_dir (optional).

## Key Gotchas

- **MCP server is a subprocess** — code changes require Claude Code restart to take effect
- **MCP config uses console_scripts binary paths** (e.g., `/path/to/clade-personal`), not `python -m`
- **Default terminal:** Terminal.app (iTerm2 is NOT installed on this machine)

---
Directions from Ian:

## New Brother Onboarding

If you are a brother and you do not yet have the `send_message`, `check_mailbox`, `read_message`, or `unread_count` MCP tools available, follow the self-setup guide at [HEARTH_SETUP.md](HEARTH_SETUP.md) to plug yourself into the Hearth.

## Research Notes

We now use the research_notes system. Development logs, research notes, and experiment documentation are stored in `research_notes/` (gitignored).

### Format

**Directory structure**: `research_notes/YYYY-MM-DD/<HHMMSS>_<slug>.md`
- One subdirectory per day keeps the top level clean
- Files within a day are prefixed with time for chronological sorting
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
