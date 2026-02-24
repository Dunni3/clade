# Operations Guide

CLI commands, deployment, infrastructure, and environment setup. For system internals, see [architecture.md](architecture.md).

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

See [QUICKSTART.md](QUICKSTART.md) for first-time setup walkthrough.

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

Brothers on SLURM clusters are **intermittently available** — online only while the job is running. See [cluster-tailscale-setup.md](cluster-tailscale-setup.md) for full details and troubleshooting.

**Tailscale + Ember:** `clade setup-ember` auto-detects the brother's Tailscale IP and uses it as the `ember_host` in config. This means Ember health checks and future Conductor calls route through the Tailscale mesh, bypassing firewalls. If Tailscale isn't available, it falls back to the SSH hostname.

## Docker Compose Test Environment

A multi-container environment for full end-to-end testing of the CLI onboarding flow, Ember delegation, and Conductor orchestration without real SSH hosts or a deployed Hearth. See [docker-testing.md](docker-testing.md) for full details.

```bash
bash scripts/test-compose.sh   # keygen + build + start + attach to personal container
```

Four containers: `personal` (coordinator), `worker` (sshd + Ember), `hearth` (FastAPI + conductor config), `frontend` (Vite dev server at `localhost:5173`). Pre-configured test API keys. Claude Code auth via `ANTHROPIC_API_KEY` in `docker/.env` (gitignored).
