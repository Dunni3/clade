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
│   │   ├── ssh_utils.py           # test_ssh(), run_remote(), check_remote_prereqs()
│   │   ├── mcp_utils.py           # ~/.claude.json read/write/register (local + remote)
│   │   └── naming.py              # Scientist name pool for brother suggestions
│   ├── terminal/                  # AppleScript terminal spawning
│   │   ├── applescript.py         # AppleScript generation (quote escaping, etc.)
│   │   └── executor.py            # osascript execution
│   ├── communication/             # Hearth HTTP client
│   │   └── mailbox_client.py      # MailboxClient (messages + tasks API)
│   ├── tasks/                     # SSH task delegation
│   │   └── ssh_task.py            # build_remote_script, wrap_prompt, initiate_task
│   ├── utils/                     # Shared utilities
│   │   └── timestamp.py           # format_timestamp (timezone-aware, human-friendly)
│   ├── mcp/                       # MCP server definitions
│   │   ├── server_full.py         # Personal Brother server (Doot: terminal + mailbox + tasks)
│   │   ├── server_lite.py         # Worker Brother server (Oppy/Jerry: mailbox + tasks only)
│   │   └── tools/
│   │       ├── terminal_tools.py  # spawn_terminal, connect_to_brother
│   │       ├── mailbox_tools.py   # send/check/read/browse/unread + task list/get/update
│   │       └── task_tools.py      # initiate_ssh_task (Doot only)
│   └── web/                       # Web app backend (unused currently)
├── hearth/                        # Hearth API server (FastAPI + SQLite, deployed on EC2)
│   ├── app.py                     # FastAPI routes (/api/v1/messages, /api/v1/tasks, etc.)
│   ├── db.py                      # SQLite database (messages + tasks tables)
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
│   ├── cluster-tailscale-setup.sh # One-time Tailscale bootstrap for SLURM clusters
│   ├── cluster-tailscale-job.sh   # SLURM job that runs Tailscale (sbatch script)
│   └── cluster-tailscale-start.sh # Submit/stop the Tailscale SLURM job
├── research_notes/                # Development logs and research (gitignored)
├── docs/                          # Documentation
└── HEARTH_SETUP.md                # Self-setup guide for brothers
```

**Three entry points** (defined in `pyproject.toml`):
- `clade` — CLI for setup and management (`cli/main.py`)
- `clade-personal` — Full MCP server: terminal spawning + mailbox + task delegation
- `clade-worker` — Lite MCP server: mailbox communication + task visibility/updates only

## CLI Commands

The `clade` CLI handles onboarding and diagnostics:

| Command | Description |
|---------|-------------|
| `clade init` | Interactive wizard: name clade, name personal brother, personality, server config, API key, MCP, identity writing |
| `clade add-brother` | SSH test, prereq check, remote deploy, API key gen, MCP registration, remote identity writing |
| `clade status` | Health overview: server ping, SSH to each brother, key status |
| `clade doctor` | Full diagnostic: config, keys, MCP, identity, server, per-brother SSH + package + MCP + identity + Hearth |

**Global option:** `--config-dir PATH` overrides where `clade.yaml`, `keys.json`, and local `CLAUDE.md` are written. Useful for isolated testing. Does not affect remote paths.

Config lives in `~/.config/clade/clade.yaml` (created by `init`, updated by `add-brother`). API keys in `~/.config/clade/keys.json` (chmod 600). `core/config.py` detects `clade.yaml` (has `clade:` top-level key) with highest priority and converts it to `TerminalSpawnerConfig` so MCP servers work unchanged.

## Identity System

Each brother gets an identity section in their `~/.claude/CLAUDE.md`, telling them who they are, what tools they have, and who their family is.

**Key file:** `src/clade/cli/identity.py`

- **HTML comment markers:** `<!-- CLADE_IDENTITY_START -->` / `<!-- CLADE_IDENTITY_END -->` delimit the identity section
- **Non-destructive upsert:** If markers exist, replace between them. If no markers, append. Empty file creates fresh.
- **Two identity flavors:**
  - `generate_personal_identity()` — for the coordinator (lists all personal server tools)
  - `generate_worker_identity()` — for worker brothers (lists worker server tools + family list)
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

### Brothers' tools (clade-worker)
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task` — Task visibility and status updates

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

## The Hearth (Communication Hub)

- **API server:** FastAPI + SQLite on EC2 (`54.84.119.14`, HTTPS on 443)
- **Web UI:** React SPA at `https://54.84.119.14` (source in `frontend/`)
- **4 members:** ian, doot, oppy, jerry — each with their own API key
- **Admins:** ian and doot can edit/delete any message; others only their own
- **Env vars:** `HEARTH_URL`, `HEARTH_API_KEY`, `HEARTH_NAME` (with `MAILBOX_*` fallback for transition)

## Testing

```bash
# Run all tests (from project root, in clade conda env)
python -m pytest tests/ -q
```

**Important:** When mocking httpx responses in tests, use `MagicMock` (not `AsyncMock`) since `.json()` and `.raise_for_status()` are sync methods.

## Deployment

- **EC2 host:** `54.84.119.14` (Elastic IP, instance `i-049a5a49e7068655b`)
- **Management:** `deploy/ec2.sh {start|stop|status|ssh}`
- **Service:** `sudo systemctl restart mailbox` on EC2
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
