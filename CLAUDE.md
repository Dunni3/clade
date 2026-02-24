# The Clade

Infrastructure for networks of Claude Code instances — inter-agent communication, task delegation, and orchestration. Designed by [Ian Dunn](https://github.com/dunni3).

## Project Structure

```
clade/
├── src/clade/          # Main package
│   ├── core/           # Config, brothers registry, types
│   ├── cli/            # CLI commands (`clade` entry point)
│   ├── communication/  # Hearth HTTP client (mailbox_client.py)
│   ├── tasks/          # SSH task delegation (ssh_task.py)
│   ├── templates/      # Jinja2 runner script templates
│   ├── worker/         # Ember server + runner + client
│   ├── mcp/            # MCP server definitions + tools/
│   ├── skills/         # Bundled skills (SKILL.md format)
│   └── utils/          # Shared utilities
├── hearth/             # Hearth API server (FastAPI + SQLite)
├── frontend/           # Web UI (Vite + React + TypeScript + Tailwind v4)
├── tests/              # Unit + integration tests
├── docker/             # Docker Compose test environment
├── deploy/             # Deployment scripts, systemd units, Tailscale
├── docs/               # Documentation
└── HEARTH_SETUP.md     # Self-setup guide for brothers
```

**Five entry points** (defined in `pyproject.toml`):
- `clade` — CLI for setup and management (`cli/main.py`)
- `clade-personal` — Full MCP server: mailbox + task delegation + ember + brother listing
- `clade-worker` — Lite MCP server: mailbox communication + task visibility/updates + ember
- `clade-ember` — Ember server: HTTP listener for task execution on worker machines
- `clade-conductor` — Conductor MCP server: mailbox + trees + worker delegation

## Key Concepts

**Task Delegation** — Two paths: Ember (HTTP, primary) and SSH (legacy). Coordinator/worker calls `initiate_ember_task()`, Hearth creates the task, Ember launches a tmux session with Claude. Runner scripts use Jinja2 templates in `src/clade/templates/`. Tasks support deferred dependencies via `blocked_by_task_id`. Lifecycle: `pending` → `launched` → `in_progress` → `completed` / `failed` / `killed`. Key files: `src/clade/tasks/ssh_task.py`, `src/clade/worker/runner.py`, `src/clade/mcp/tools/delegation_tools.py`. See [docs/architecture.md](docs/architecture.md#task-delegation-system).

**Ember Server** — Lightweight FastAPI server on worker machines (`src/clade/worker/ember.py`) that accepts task execution requests over HTTP. Runs 24/7 as a systemd service, separate from the MCP server. Uses git worktree isolation per task. Auth via `HEARTH_API_KEY`. See [docs/architecture.md](docs/architecture.md#ember-server-http-based-task-execution).

**Conductor (Kamaji)** — Periodic orchestrator on the Hearth host that builds task trees organically. Ticks triggered by: systemd timer, task completion/failure, messages. Three tick paths: event-driven, message-driven, periodic. Key files: `src/clade/mcp/server_conductor.py`, `deploy/conductor-tick.md`. See [docs/architecture.md](docs/architecture.md#conductor--workflow-orchestration).

**The Hearth** — FastAPI + SQLite communication hub on EC2. Stores messages, tasks, morsels, kanban cards, ember registry. Web UI (React SPA) in `frontend/`. Server code in `hearth/`. Env vars: `HEARTH_URL`, `HEARTH_API_KEY`, `HEARTH_NAME`. See [docs/architecture.md](docs/architecture.md#the-hearth-communication-hub).

**Task Trees** — Parent-child task hierarchies via `parent_task_id` / `root_task_id` / `depth` columns. Each task tracks its depth (root=0, auto-computed). Root tasks can carry `metadata` (JSON dict) for tree-level config like `max_depth`. The conductor auto-links follow-up tasks using `TRIGGER_TASK_ID` env var. Frontend: React Flow graph with dagre layout. See [docs/architecture.md](docs/architecture.md#task-trees).

**Morsels** — Tagged notes for audit trails and cross-session context, linked to tasks/brothers/cards. Conductor deposits a morsel each tick. See [docs/architecture.md](docs/architecture.md#morsels).

**Kanban Board** — Shared board with columns: `backlog` → `todo` → `in_progress` → `done` → `archived`. Cards auto-sync with task status. MCP tools on all servers. See [docs/architecture.md](docs/architecture.md#kanban-board).

**Identity System** — Each brother gets an identity section in `~/.claude/CLAUDE.md` via HTML comment markers. Three flavors: personal, worker, conductor. Key file: `src/clade/cli/identity.py`. See [docs/architecture.md](docs/architecture.md#identity-system).

**Skills** — Bundled in `src/clade/skills/`. Current: `implement-card` (delegates implementation + chains a blocked review task). See [docs/architecture.md](docs/architecture.md#skills-system).

**Brothers Registry** — Built at runtime from `clade.yaml` + `keys.json` via `load_brothers_registry()` in `clade_config.py`. No caching — edits take effect immediately. See [docs/architecture.md](docs/architecture.md#brothers-registry-runtime).

**MCP Tools** — Three server types with different tool sets. See [docs/mcp-tools.md](docs/mcp-tools.md).

**CLI & Deployment** — `clade init`, `clade add-brother`, `clade deploy`, `clade doctor`, etc. See [docs/operations.md](docs/operations.md).

## Testing

```bash
python -m pytest tests/ -q
```

**Important:** When mocking httpx responses in tests, use `MagicMock` (not `AsyncMock`) since `.json()` and `.raise_for_status()` are sync methods.

Docker Compose test environment: `bash scripts/test-compose.sh`. See [docs/operations.md](docs/operations.md#docker-compose-test-environment).

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
