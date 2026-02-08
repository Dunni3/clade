# Terminal Spawner - Quick Start Guide

Terminal Spawner is an MCP server that enables Claude Code instances (like Doot, Oppy, and Jerry) to spawn terminal windows and communicate with each other via a shared mailbox.

## Prerequisites

- Python 3.10 or higher
- Claude Code installed
- SSH access to remote machines (for brother connections)

## Installation

### For Doot (Local Claude Code)

```bash
cd ~/projects/terminal-spawner
source ~/opt/miniconda3/etc/profile.d/conda.sh
conda activate terminal-spawner
pip install -e .
```

This installs two entry points:
- `terminal-spawner` - Full MCP server (terminal spawning + mailbox)
- `terminal-spawner-lite` - Lite MCP server (mailbox only)

### For Oppy/Jerry (Remote Claude Code)

See [BROTHER_SETUP.md](BROTHER_SETUP.md) for detailed instructions on setting up remote brothers.

## Configuration

### Register MCP Server with Claude Code

**For Doot (local):**

Edit `~/.claude.json` and add:

```json
{
  "mcpServers": {
    "terminal-spawner": {
      "command": "terminal-spawner",
      "env": {
        "MAILBOX_URL": "https://34.235.130.130",
        "MAILBOX_API_KEY": "your-api-key-here",
        "MAILBOX_NAME": "doot"
      }
    }
  }
}
```

**For Oppy/Jerry (remote):**

```json
{
  "mcpServers": {
    "brother-mailbox": {
      "command": "terminal-spawner-lite",
      "env": {
        "MAILBOX_URL": "https://34.235.130.130",
        "MAILBOX_API_KEY": "your-api-key-here",
        "MAILBOX_NAME": "oppy"
      }
    }
  }
}
```

### (Optional) Create Brother Configuration

By default, terminal-spawner knows about `jerry` (cluster) and `oppy` (masuda). To customize or add brothers, create a config file:

**Location options** (checked in order):
1. `~/.config/terminal-spawner/config.yaml`
2. `$XDG_CONFIG_HOME/terminal-spawner/config.yaml`
3. `~/.terminal-spawner.yaml`

**Example config:**

```yaml
default_terminal_app: terminal  # or "iterm2"

brothers:
  jerry:
    host: cluster
    working_dir: null
    description: "Brother Jerry — GPU jobs on the cluster"

  oppy:
    host: masuda
    working_dir: "~/projects/mol_diffusion/OMTRA_oppy"
    description: "Brother Oppy — The architect on masuda"

  # Add custom brothers
  dev-vm:
    host: dev.example.com
    working_dir: "~/workspace"
    description: "Development VM"
```

The `command` field is auto-generated from `host` and `working_dir` if not specified.

See `examples/config.yaml.example` for a full example.

## Restart Claude Code

After configuring the MCP server, restart Claude Code to load the new server.

## Verify Installation

After restarting Claude Code, you should see these MCP tools available:

**Doot (full server):**
- `spawn_terminal` - Open new terminal window
- `connect_to_brother` - Connect to Oppy/Jerry
- `list_brothers` - List available brothers
- `send_message` - Send message to brothers
- `check_mailbox` - Check for messages
- `read_message` - Read a message
- `browse_feed` - Browse all messages
- `unread_count` - Get unread count

**Oppy/Jerry (lite server):**
- `send_message`
- `check_mailbox`
- `read_message`
- `browse_feed`
- `unread_count`

## Basic Usage

### Spawn a Terminal Window

**As Doot:**
```
spawn_terminal(command="htop")
```

### Connect to a Brother

**As Doot:**
```
connect_to_brother(name="jerry")
```

This opens a Terminal.app window with an SSH session to Jerry running Claude Code.

### Send a Message

**As any brother:**
```
send_message(recipients=["oppy"], body="Can you review the training script?", subject="Code review")
```

### Check Messages

**As any brother:**
```
check_mailbox(unread_only=true)
```

### Browse Message Feed

**As any brother:**
```
browse_feed(sender="doot", limit=20)
```

## Troubleshooting

### MCP server not loading

1. Check `~/.claude.json` for syntax errors
2. Verify entry point is installed: `which terminal-spawner`
3. Check Claude Code logs for errors

### Brother connection fails

1. Verify SSH access: `ssh cluster` (or `ssh masuda`)
2. Check that Claude Code is installed on remote machine
3. Verify `working_dir` exists on remote machine

### Mailbox not working

1. Verify environment variables are set in `~/.claude.json`
2. Check mailbox server is running: See [MAILBOX_SETUP.md](MAILBOX_SETUP.md)
3. Verify API key is correct

## Next Steps

- [Set up the mailbox server](MAILBOX_SETUP.md)
- [Configure remote brothers](BROTHER_SETUP.md)
- [Explore future features](FUTURE.md)

## Support

For issues and questions:
- Check the documentation in `docs/`
- Review the example config: `examples/config.yaml.example`
- File an issue on GitHub
