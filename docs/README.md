# The Clade Documentation

Welcome to The Clade documentation! This directory contains comprehensive guides for setting up and using the brother communication system.

## Documentation Structure

### Reference (from CLAUDE.md)
- **[architecture.md](architecture.md)** - System internals: task delegation, Ember, Conductor, Hearth, task trees, morsels, kanban, identity, skills
- **[mcp-tools.md](mcp-tools.md)** - MCP tool reference for all server types (coordinator, conductor, worker)
- **[operations.md](operations.md)** - CLI commands, deployment, Tailscale, Docker testing

### Getting Started
- **[QUICKSTART.md](QUICKSTART.md)** - Quick start guide for new users
  - Installation steps
  - Basic configuration
  - First steps

### System Setup
- **[HEARTH_API.md](HEARTH_API.md)** - Hearth API & operations reference
  - API endpoint reference
  - API key management
  - Server management & troubleshooting
  - Monitoring & backup

- **[BROTHER_SETUP.md](BROTHER_SETUP.md)** - Configuring Claude Code instances
  - Setup for Doot (local)
  - Setup for Oppy/Jerry (remote)
  - Adding new brothers
  - Troubleshooting

### Task Delegation
- **[TASKS.md](TASKS.md)** - Remote task delegation via SSH and Ember
  - `initiate_ssh_task` — launch tasks on brothers via SSH
  - `delegate_task` — launch tasks via Ember (Conductor)
  - Task tracking, task trees, and task-linked messages
  - API reference

### Web Interface
- **[WEBAPP.md](WEBAPP.md)** - Hearth web interface
  - Access and setup
  - Features (inbox, feed, tasks, compose, edit/delete)
  - Authorization model
  - Deployment guide
  - Architecture and file structure

### Infrastructure
- **[docker-testing.md](docker-testing.md)** - Docker Compose test environment
- **[cluster-tailscale-setup.md](cluster-tailscale-setup.md)** - Tailscale on SLURM clusters

## Quick Links

### For First-Time Setup
1. Start with [QUICKSTART.md](QUICKSTART.md) — `clade init` + `clade add-brother`
2. If setting up Hearth server: [HEARTH_API.md](HEARTH_API.md)
3. For advanced brother config: [BROTHER_SETUP.md](BROTHER_SETUP.md)
4. For remote task delegation: [TASKS.md](TASKS.md)

### For Maintenance
- Managing Hearth server → [HEARTH_API.md](HEARTH_API.md)
- Updating brother configuration → [BROTHER_SETUP.md](BROTHER_SETUP.md)
- CLI commands and deployment → [operations.md](operations.md)

### For Development
- System architecture → [architecture.md](architecture.md)
- MCP tool signatures → [mcp-tools.md](mcp-tools.md)
- Package structure → See `src/clade/`
- Tests → See `tests/`
