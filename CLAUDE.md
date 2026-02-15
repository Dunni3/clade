# The Clade

Infrastructure for a family of Claude Code instances — inter-agent communication, task delegation, and orchestration.

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
│   │   ├── conductor_setup.py     # Conductor (Kamaji) deployment logic
│   │   └── setup_conductor_cmd.py # `clade setup-conductor` — deploy Conductor on Hearth server
│   ├── terminal/                  # AppleScript terminal spawning
│   │   ├── applescript.py         # AppleScript generation (quote escaping, etc.)
│   │   └── executor.py            # osascript execution
│   ├── communication/             # Hearth HTTP client
│   │   └── mailbox_client.py      # MailboxClient (messages + tasks API)
│   ├── tasks/                     # SSH task delegation
│   │   └── ssh_task.py            # build_remote_script, wrap_prompt, initiate_task
│   ├── worker/                    # Ember server (HTTP-based task execution on workers)
│   │   ├── auth.py                # Bearer token auth (reuses HEARTH_API_KEY)
│   │   ├── runner.py              # Local tmux task launcher (like ssh_task without SSH)
│   │   ├── ember.py               # FastAPI Ember server (endpoints + in-memory state)
│   │   └── client.py              # EmberClient (httpx client for Ember API)
│   ├── utils/                     # Shared utilities
│   │   └── timestamp.py           # format_timestamp (timezone-aware, human-friendly)
│   ├── mcp/                       # MCP server definitions
│   │   ├── server_full.py         # Personal Brother server (Doot: terminal + mailbox + tasks + ember)
│   │   ├── server_lite.py         # Worker Brother server (Oppy/Jerry: mailbox + tasks + ember only)
│   │   ├── server_conductor.py    # Conductor server (Kamaji: mailbox + thrums + delegation)
│   │   └── tools/
│   │       ├── terminal_tools.py  # spawn_terminal, connect_to_brother
│   │       ├── mailbox_tools.py   # send/check/read/browse/unread + task list/get/update
│   │       ├── task_tools.py      # initiate_ssh_task (Doot only)
│   │       ├── ember_tools.py     # check_ember_health, list_ember_tasks
│   │       ├── thrum_tools.py     # create/list/get/update thrums
│   │       └── conductor_tools.py # delegate_task, check_worker_health, list_worker_tasks
│   └── web/                       # Web app backend (unused currently)
├── hearth/                        # Hearth API server (FastAPI + SQLite, deployed on EC2)
│   ├── app.py                     # FastAPI routes (/api/v1/messages, /api/v1/tasks, etc.)
│   ├── db.py                      # SQLite database (messages, tasks, api_keys tables)
│   ├── auth.py                    # API key authentication
│   ├── models.py                  # Pydantic request/response models
│   └── config.py                  # Server configuration
├── tests/                         # All tests
│   ├── unit/                      # Fast, no network (config, applescript, client, ssh, cli, timestamp)
│   └── integration/               # MCP tool + Hearth server integration tests
├── frontend/                      # Hearth web UI (Vite + React + TypeScript + Tailwind v4)
├── deploy/                        # Deployment and infrastructure scripts
│   ├── setup.sh                   # EC2 server provisioning
│   ├── ec2.sh                     # EC2 instance management (start/stop/status/ssh)
│   ├── ember.service              # systemd unit for Ember server on masuda
│   ├── conductor-tick.sh          # Conductor tick script (runs Kamaji's periodic check-in)
│   ├── conductor-tick.md          # Conductor tick prompt (Kamaji's instructions)
│   ├── conductor-tick.service     # systemd oneshot service for conductor tick
│   ├── conductor-tick.timer       # systemd timer (every 15 min)
│   ├── conductor-workers.yaml     # Example worker registry for the conductor
│   ├── conductor.env.example      # Example conductor env file
│   ├── cluster-tailscale-setup.sh # One-time Tailscale bootstrap for SLURM clusters
│   ├── cluster-tailscale-job.sh   # SLURM job that runs Tailscale (sbatch script)
│   └── cluster-tailscale-start.sh # Submit/stop the Tailscale SLURM job
├── research_notes/                # Development logs and research (gitignored)
├── docs/                          # Documentation
└── HEARTH_SETUP.md                # Self-setup guide for brothers
```

**Five entry points** (defined in `pyproject.toml`):
- `clade` — CLI for setup and management (`cli/main.py`)
- `clade-personal` — Full MCP server: terminal spawning + mailbox + task delegation + ember
- `clade-worker` — Lite MCP server: mailbox communication + task visibility/updates + ember
- `clade-ember` — Ember server: HTTP listener for task execution on worker machines
- `clade-conductor` — Conductor MCP server: mailbox + thrums + worker delegation (used by Kamaji)

## CLI Commands

The `clade` CLI handles onboarding and diagnostics:

| Command | Description |
|---------|-------------|
| `clade init` | Interactive wizard: name clade, name personal brother, personality, server config, API key gen + registration (`--server-key`), MCP, identity writing |
| `clade add-brother` | SSH test, prereq check, remote deploy, API key gen + Hearth registration, MCP registration, remote identity writing. `--ember` flag adds Ember setup. |
| `clade setup-ember` | Deploy an Ember server on an existing brother: detect binary/user/Tailscale IP, template systemd service, start + health check |
| `clade setup-conductor` | Deploy the Conductor (Kamaji) on the Hearth server: config files, systemd timer, identity. Idempotent — re-run to update workers config. |
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
- **Personality:** Optional free-text description stored in `clade.yaml`, included in the identity section
- **Local writing:** `write_identity_local()` reads/upserts/writes `~/.claude/CLAUDE.md`
- **Remote writing:** `write_identity_remote()` base64-encodes the identity, SSHes to remote, runs a Python upsert script
- **`--no-identity`:** Both `init` and `add-brother` accept this flag to skip identity writing
- **Doctor checks:** WARN-level checks for local and remote identity presence (not failures)

## MCP Tools

### Doot's tools (clade-personal)
- `spawn_terminal(command?, app?)` — Open Terminal.app window, optionally run a command
- `connect_to_brother(name)` — SSH + Claude Code session to oppy or jerry
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `initiate_ssh_task(brother, prompt, subject?, max_turns?, auto_pull?)` — Delegate a task via SSH + tmux
- `list_tasks(assignee?, status?, limit?)` — Browse tasks
- `check_ember_health(url?)` — Check Ember server health (optional URL for ad-hoc checks)
- `list_ember_tasks()` — List active tasks and orphaned tmux sessions on configured Ember

### Kamaji's tools (clade-conductor)
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task` — Task visibility and status updates
- `create_thrum(subject, description?, plan?)` — Create a new thrum (workflow)
- `list_thrums(status?, limit?)` — List thrums
- `get_thrum(thrum_id)` — Get thrum details with linked tasks
- `update_thrum(thrum_id, status?, plan?, output?)` — Update thrum status/plan/output
- `delegate_task(worker, prompt, subject?, thrum_id?, max_turns?, working_dir?)` — Delegate a task to a worker via Ember
- `check_worker_health(worker?)` — Check one or all worker Ember servers
- `list_worker_tasks(worker?)` — List active tasks on worker Embers

### Brothers' tools (clade-worker)
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task` — Task visibility and status updates
- `check_ember_health(url?)` — Check local Ember server health
- `list_ember_tasks()` — List active tasks on local Ember

## Task Delegation System

Doot can delegate tasks to brothers via SSH. The flow:

1. Doot calls `initiate_ssh_task(brother, prompt)`
2. Task is created in the Hearth database (status: `pending`)
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

Key file: `src/clade/tasks/ssh_task.py` — contains `build_remote_script()`, `wrap_prompt()`, `initiate_task()`

## Ember Server (HTTP-based Task Execution)

An **Ember** is a lightweight HTTP server running on a worker brother's machine that accepts task execution requests. It replaces SSH-based delegation with HTTP triggers, enabling the future Conductor (Kamaji) to orchestrate tasks without SSH access.

**Architecture:** The Ember is a separate process from the `clade-worker` MCP server. The MCP server's lifecycle is tied to a Claude Code session (stdio transport). The Ember runs 24/7, waiting for incoming task requests even when no Claude session is active.

**Key files:**
- `src/clade/worker/ember.py` — FastAPI app with endpoints
- `src/clade/worker/runner.py` — Local tmux launcher (reuses `generate_session_name()` and `wrap_prompt()` from `ssh_task.py`)
- `src/clade/worker/auth.py` — Bearer token auth
- `src/clade/worker/client.py` — `EmberClient` for calling Ember APIs

**Endpoints:**
| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | No | Liveness check (brother name, active tasks, uptime) |
| `POST /tasks/execute` | Yes (202) | Launch a Claude Code tmux session. Returns busy error if already running a task. |
| `GET /tasks/active` | Yes | Active task info + orphaned tmux sessions |

**Authentication:** Embers reuse the brother's Hearth API key (`HEARTH_API_KEY` env var) — no separate Ember key needed. Doot authenticates to a remote Ember using the brother's Hearth key (from `keys.json`). Workers authenticate to their local Ember using their own Hearth key.

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
- Doot: `EMBER_URL=http://100.71.57.52:8100` + `EMBER_API_KEY=<brother's Hearth key>`

**In-memory state:** `TaskState` tracks one active task. No DB — the Hearth is source of truth. `is_busy()` checks tmux liveness and auto-clears stale tasks.

**Deployment:** Automated via `clade setup-ember <name>` or `clade add-brother --ember`. The CLI detects the remote user, `clade-ember` binary path, clade package directory, and Tailscale IP, then templates and deploys a systemd service. Falls back to printing manual instructions if sudo is unavailable. Reference service file: `deploy/ember.service`. Config fields `ember_host` and `ember_port` are stored in `BrotherEntry` in `clade.yaml`.

## Conductor (Kamaji) — Workflow Orchestration

The **Conductor** (named Kamaji) is a periodic process that orchestrates multi-step workflows ("thrums") by delegating tasks to worker brothers via their Ember servers. It runs on the same EC2 host as the Hearth.

**Architecture:** A systemd timer triggers a "tick" every 15 minutes. Each tick spawns a Claude Code session with the `clade-conductor` MCP server, which reads a prompt (`conductor-tick.md`) that instructs Kamaji to check mailbox, review active thrums, delegate tasks, and report status.

**Thrums:** A thrum is a multi-step workflow tracked in the Hearth database. Lifecycle: `pending` -> `planning` -> `active` -> `completed` / `failed`. Each thrum can have a plan and linked tasks. The Conductor checks thrum progress each tick and delegates the next step when ready.

**Key files:**
- `src/clade/mcp/server_conductor.py` — MCP server (mailbox + thrums + delegation tools)
- `src/clade/mcp/tools/thrum_tools.py` — Thrum CRUD tools
- `src/clade/mcp/tools/conductor_tools.py` — Worker delegation tools
- `src/clade/cli/conductor_setup.py` — Deployment logic
- `src/clade/cli/setup_conductor_cmd.py` — `clade setup-conductor` CLI command
- `deploy/conductor-tick.sh` — Tick runner script
- `deploy/conductor-tick.md` — Tick prompt (Kamaji's instructions)

**Deployment flow:**
```
clade init → clade add-brother --ember → clade setup-conductor
```

The command is separate from `init` because the Conductor needs brother Ember info that only exists after `add-brother --ember`. It's idempotent — re-run to update the workers config when brothers change.

**What `clade setup-conductor` does:**
1. SSHes to the Hearth server (`server.ssh` in clade.yaml)
2. Deploys/updates the clade package
3. Generates Kamaji's API key (idempotent) and registers with the Hearth
4. Builds `conductor-workers.yaml` from brothers with `ember_host` set
5. Builds `conductor.env` and `conductor-mcp.json`
6. Writes all config files to `~/.config/clade/` on the remote
7. Copies tick script + prompt to `~/.config/clade/`
8. Deploys systemd service + timer, enables and starts the timer
9. Writes Kamaji's identity to remote `~/.claude/CLAUDE.md`

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

- **API server:** FastAPI + SQLite on EC2 (`54.84.119.14`, HTTPS on 443)
- **Web UI:** React SPA at `https://54.84.119.14` (source in `frontend/`)
- **5 members:** ian, doot, oppy, jerry, kamaji — each with their own API key
- **Admins:** ian and doot can edit/delete any message; others only their own
- **Env vars:** `HEARTH_URL`, `HEARTH_API_KEY`, `HEARTH_NAME` (with `MAILBOX_*` fallback for transition)
- **Dynamic key registration:** API keys can be registered via `POST /api/v1/keys` (any authenticated user). The CLI does this automatically during `clade init --server-key`, `clade add-brother`, and `clade setup-conductor`. Auth checks env-var keys first (fast), then falls back to DB-registered keys.
- **Thrums API:** `/api/v1/thrums` endpoints for creating, listing, getting, and updating thrums (multi-step workflows). Used by the Conductor.

## Testing

```bash
# Run all tests (from project root, in clade conda env)
python -m pytest tests/ -q
```

**Important:** When mocking httpx responses in tests, use `MagicMock` (not `AsyncMock`) since `.json()` and `.raise_for_status()` are sync methods.

## Deployment

- **EC2 host:** `54.84.119.14` (Elastic IP, instance `i-049a5a49e7068655b`)
- **Management:** `deploy/ec2.sh {start|stop|status|ssh}`
- **Hearth service:** `sudo systemctl restart mailbox` on EC2
- **Conductor timer:** `sudo systemctl restart conductor-tick.timer` on EC2 (deployed via `clade setup-conductor`)
- **Web UI deploy:** `frontend/` -> `npm run build` -> SCP `dist/` to EC2 -> copy to `/var/www/mailbox/`
  - `/var/www/mailbox/` is owned by `www-data`, so direct SCP as `ubuntu` fails with permission denied
  - **Correct pattern:** SCP to `/tmp/mailbox-deploy/`, then `sudo cp -r` to `/var/www/mailbox/`:
    ```bash
    ssh -i ~/.ssh/moltbot-key.pem ubuntu@54.84.119.14 "mkdir -p /tmp/mailbox-deploy"
    scp -i ~/.ssh/moltbot-key.pem -r frontend/dist/* ubuntu@54.84.119.14:/tmp/mailbox-deploy/
    ssh -i ~/.ssh/moltbot-key.pem ubuntu@54.84.119.14 "sudo rm -rf /var/www/mailbox/* && sudo cp -r /tmp/mailbox-deploy/* /var/www/mailbox/ && sudo chown -R www-data:www-data /var/www/mailbox/ && rm -rf /tmp/mailbox-deploy"
    ```

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

## Key Gotchas

- **MCP server is a subprocess** — code changes require Claude Code restart to take effect
- **Heredoc quoting:** Unquoted delimiter = variable expansion ON. The runner script heredoc must be unquoted so temp file paths expand, but `$(...)` must be escaped
- **Default terminal:** Terminal.app (iTerm2 is NOT installed on this machine)
- **EC2 deployment paths** still use old naming (mailbox.service, /opt/mailbox/, /var/www/mailbox/) — to be renamed in a future deployment update

---
Directions from Ian:

## New Brother Onboarding

If you are a brother (Oppy, Jerry, or a future brother) and you do not yet have the `send_message`, `check_mailbox`, `read_message`, or `unread_count` MCP tools available, follow the self-setup guide at [HEARTH_SETUP.md](HEARTH_SETUP.md) to plug yourself into the Hearth.

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
