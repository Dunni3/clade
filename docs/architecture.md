# Architecture Deep Dive

Detailed internals for each Clade subsystem. For a high-level overview, see the root [CLAUDE.md](../CLAUDE.md).

## Task Delegation System

Two delegation paths exist. **Ember (HTTP) is the primary path**; SSH is legacy.

### Ember Delegation (primary)

1. Coordinator/worker calls `initiate_ember_task(brother, prompt, ...)`
2. Task is created in the Hearth database (status: `pending`). If `parent_task_id` is set, the task is linked as a child.
3. If `blocked_by_task_id` is set and the blocker hasn't completed, the task stays `pending` — auto-delegated server-side when the blocker completes (see Deferred Dependencies below).
4. Otherwise, the task is sent to the brother's Ember server via HTTP, which launches a tmux session running `claude -p "<prompt>" --dangerously-skip-permissions`.

See also [TASKS.md](TASKS.md) for the task delegation user guide.

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
- **`metadata`**: Arbitrary JSON dict stored on tasks (typically root tasks). Used for tree-level configuration like `max_depth`. Serialized to JSON TEXT in SQLite, deserialized on retrieval.
- **`depth`**: Integer tracking a task's position in its tree (root = 0, children = 1, etc.). Auto-computed on insert from `parent.depth + 1`. Cascades on reparenting via recursive CTE.

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

**DB schema:** `parent_task_id`, `root_task_id`, `depth`, and `metadata` columns on the tasks table. Every standalone task has `root_task_id = self.id` and `depth = 0` (single-node tree). When a child is created, it inherits `root_task_id` from its parent and gets `depth = parent.depth + 1`.

**Depth tracking:** Each task stores its depth in the tree (root = 0). Depth is auto-computed on insert and cascaded on reparenting (via recursive CTE that shifts all descendants by the delta). This enables O(1) depth lookups without traversal.

**Task metadata:** Tasks accept an optional `metadata` dict (stored as JSON TEXT). This is the extension mechanism for tree-level configuration. Currently used for:
- `max_depth` — Maximum tree depth the conductor should respect (default: 15 in conductor prompt). The conductor checks `root_task.metadata.max_depth` before delegating children. This is a **soft guardrail** enforced by the conductor prompt, not a database constraint.

Metadata is typically set on root tasks and read by looking up the tree's root. Future uses could include strategy hints, retry policies, or priority escalation rules.

**API:** `GET /api/v1/trees` returns root tasks with per-status child counts. `GET /api/v1/trees/{root_id}` returns the full recursive tree with depth and metadata on every node. `POST /api/v1/tasks` accepts optional `parent_task_id` and `metadata`; `root_task_id` and `depth` are auto-computed.

**Frontend:** TreeListPage shows all trees with status breakdown pills. TreeDetailPage renders an interactive React Flow graph (dagre layout) with status-colored nodes, click-to-inspect side panel, animated edges for in-progress tasks. Task detail shows depth badge (when > 0) and metadata key-value pills. Dependencies: `@xyflow/react`, `dagre`.

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

**Guardrails:** Configurable max tree depth via `metadata.max_depth` on root tasks (default 15, enforced in conductor prompt), max 2 retries (prefer `retry_task()` for failed tasks), check worker aspen load before delegating. The conductor deposits a morsel at the end of every tick summarizing observations and actions.

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
- **Task trees:** Tasks support parent-child relationships via `parent_task_id`, `root_task_id`, `depth`, and `metadata` columns. Trees grow organically as the conductor delegates follow-up tasks. `depth` is auto-computed (root=0, child=parent+1) and cascaded on reparenting. `metadata` is a JSON dict for tree-level config (e.g. `max_depth`). API: `GET /api/v1/trees` (list with status summaries), `GET /api/v1/trees/{root_id}` (full recursive tree with depth/metadata). `POST /api/v1/tasks` accepts optional `parent_task_id` and `metadata`; `root_task_id` and `depth` are auto-computed.
- **Morsels:** Structured observation repository. Any brother can deposit a morsel (text note tagged with keywords and linked to tasks/brothers). Tables: `morsels`, `morsel_tags`, `morsel_links`. API: `POST /api/v1/morsels`, `GET /api/v1/morsels` (filtered by creator/tag/linked object), `GET /api/v1/morsels/{id}`.
- **Ember registry (DB-backed):** Ember URLs stored in `embers` table instead of env var. API: `PUT /api/v1/embers/{name}` (register/update), `GET /api/v1/embers` (list), `DELETE /api/v1/embers/{name}` (admin). `GET /api/v1/embers/status` merges DB entries with `EMBER_URLS` env var (DB wins on conflict). `clade setup-ember` auto-registers after deployment.
- **Task events:** `POST /api/v1/tasks/{task_id}/log` — log events (tool calls, progress updates) against a task. Events stored in `task_events` table and returned with task detail.
- **Kill endpoint:** `POST /api/v1/tasks/{id}/kill` — proxies to the assignee's Ember to terminate the tmux session, then marks the task `killed` in DB. Only creator or admins can kill. Returns 409 for non-active tasks. Does NOT trigger conductor ticks.
- **Retry endpoint:** `POST /api/v1/tasks/{id}/retry` — creates a child task with same prompt, delegates to Ember, copies `on_complete`. Only failed tasks can be retried. Does NOT trigger conductor ticks.
- **Deferred dependencies:** Tasks accept `blocked_by_task_id`. When the blocker completes, `_unblock_and_delegate()` auto-delegates. When the blocker fails, `_cascade_failure()` recursively fails downstream tasks.
- **Card auto-sync:** When a task moves to `in_progress`, linked kanban cards in `backlog`/`todo` auto-move to `in_progress` with updated assignee.
- **Event-driven conductor ticks:** `CONDUCTOR_TICK_CMD` env var. When set, the Hearth fires the conductor tick (fire-and-forget) on: **any** task completion/failure (not kills), messages sent to the conductor (not from itself), Task ID is passed as a positional arg; message ID is passed as `--message <id>`.

See also [MAILBOX_SETUP.md](MAILBOX_SETUP.md) for deployment guide and [WEBAPP.md](WEBAPP.md) for frontend details.

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

See also [BROTHER_SETUP.md](BROTHER_SETUP.md) for setup guide.

## Brothers Registry (Runtime)

Coordinator and workers build the brothers registry at runtime from `clade.yaml` + `keys.json` via `load_brothers_registry()` in `clade_config.py`. Each tool invocation re-reads the files — no caching, so edits take effect immediately without restarting Claude Code. Only brothers with `ember_host` set are included. Legacy fallback via `BROTHERS_CONFIG` env var.

## Skills System

Bundled skills live in `src/clade/skills/`. Each skill is a directory containing `SKILL.md` with YAML frontmatter (`name`, `description`, `argument-hint`, `disable-model-invocation`) and markdown instructions.

**Current skills:**
- `implement-card` — Reads a kanban card, delegates an implementation task to a brother via `initiate_ember_task`, then creates a blocked review task that auto-runs when implementation completes. Arguments: card_id (required), brother (default "oppy"), working_dir (optional).
