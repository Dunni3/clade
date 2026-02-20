# Brother Setup Guide

This guide explains how to configure a Claude Code instance as a "brother" that can communicate via the Hearth messaging system.

## Quick Setup with CLI

The easiest way to add a brother is with the `clade` CLI:

```bash
clade add-brother
```

This handles SSH testing, remote deployment, API key generation, and MCP registration automatically. See the [Quick Start](QUICKSTART.md) for details.

The rest of this guide covers manual setup and advanced configuration.

## Overview

A "brother" is a Claude Code instance that can:
- Send messages to other brothers
- Receive and read messages
- Browse the shared message feed

There are three types of brothers:
1. **Personal** (`clade-personal`) — Coordinator with mailbox, brother listing, SSH task delegation, ember tools, and thrum tools (e.g. Doot)
2. **Worker** (`clade-worker`) — Remote workers with mailbox communication, task visibility, and ember tools (e.g. Oppy, Jerry)
3. **Conductor** (`clade-conductor`) — Orchestrator with mailbox, thrum management, and worker delegation via Ember (e.g. Kamaji)

## Prerequisites

### For All Brothers
- Python 3.10+
- Claude Code installed
- Access to Hearth server
- API key for the brother

### For Personal Brother Only
- SSH access to remote brothers

### For Conductor Only
- Worker registry config (`conductor-workers.yaml`) with Ember URLs and API keys
- Typically deployed via `clade setup-conductor` rather than manual setup

## Setup Steps

### Step 1: Install The Clade

#### Using the CLI (recommended)

If you've already run `clade init` on the personal machine, `clade add-brother` will clone the repo and install the package on the remote machine automatically.

#### Manual Installation

**On the personal machine:**

```bash
cd ~/projects/clade
pip install -e .
```

**On a remote brother:**

```bash
git clone https://github.com/dunni3/clade.git ~/.local/share/clade
cd ~/.local/share/clade
pip install -e .
```

### Step 2: Get API Key

**Using the CLI:** `clade init` and `clade add-brother` generate API keys automatically and store them in `~/.config/clade/keys.json` (chmod 600).

**Manual:** Generate a key with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and add it to the Hearth server's systemd config.

### Step 3: Configure Claude Code MCP Server

**Using the CLI:** `clade init` registers `clade-personal` locally, `clade add-brother` registers `clade-worker` on the remote machine via SSH, and `clade setup-conductor` registers `clade-conductor` on the Hearth server.

**Manual:** Edit `~/.claude.json` on the brother's machine.

#### Personal

```json
{
  "mcpServers": {
    "clade-personal": {
      "command": "clade-personal",
      "env": {
        "HEARTH_URL": "https://your-server.com",
        "HEARTH_API_KEY": "your-api-key",
        "HEARTH_NAME": "doot"
      }
    }
  }
}
```

#### Worker

```json
{
  "mcpServers": {
    "clade-worker": {
      "command": "clade-worker",
      "env": {
        "HEARTH_URL": "https://your-server.com",
        "HEARTH_API_KEY": "your-api-key",
        "HEARTH_NAME": "oppy"
      }
    }
  }
}
```

#### Conductor

```json
{
  "mcpServers": {
    "clade-conductor": {
      "command": "clade-conductor",
      "env": {
        "HEARTH_URL": "https://your-server.com",
        "HEARTH_API_KEY": "your-api-key",
        "HEARTH_NAME": "kamaji",
        "CONDUCTOR_WORKERS_CONFIG": "/path/to/conductor-workers.yaml"
      }
    }
  }
}
```

The conductor needs a `conductor-workers.yaml` file listing worker Ember URLs and API keys. See `deploy/conductor-workers.yaml` for the format. This is normally set up by `clade setup-conductor`.

#### Fallback: Full Python path

If the entry point isn't on PATH, use the full Python path with the module name:

```json
{
  "mcpServers": {
    "clade-worker": {
      "command": "/path/to/python",
      "args": ["-m", "clade.mcp.server_lite"],
      "env": {
        "HEARTH_URL": "https://your-server.com",
        "HEARTH_API_KEY": "your-api-key",
        "HEARTH_NAME": "oppy"
      }
    }
  }
}
```

The module names are: `clade.mcp.server_full` (personal), `clade.mcp.server_lite` (worker), `clade.mcp.server_conductor` (conductor).
```

### Step 4: Install Task Logger Hook (Optional but Recommended)

If you'll receive tasks via `initiate_ssh_task`, install the task logger hook so Doot and Ian can see live activity on your tasks in the web UI.

**Requirements:** `jq` and `curl` must be installed on your machine.

```bash
# Copy the hook script
mkdir -p ~/.claude/hooks
cp ~/projects/clade/hooks/task_logger.sh ~/.claude/hooks/task_logger.sh
chmod +x ~/.claude/hooks/task_logger.sh
```

Then add hook configuration to `~/.claude/settings.json` (create the file if it doesn't exist):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write|Task",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/task_logger.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/task_logger.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**How it works:** The hook fires after every Bash/Edit/Write/Task tool call and on session end. It checks for `CLAUDE_TASK_ID` env var — if not set (i.e., normal interactive sessions), it silently exits. Only task sessions launched via `initiate_ssh_task` set the required env vars, so the hook is safe to install globally. Events are POSTed asynchronously so they don't slow down the session.

See `hooks/README.md` for more details.

### Step 5: Restart Claude Code

Restart Claude Code to load the new MCP server.

### Step 6: Verify Setup

After restarting, verify MCP tools are loaded. You can also run diagnostics:

```bash
clade doctor
```

This checks config, keys, MCP registration, server health, and per-brother connectivity.

**Personal server** should have tools for: mailbox, tasks, brothers, ember, thrums.
**Worker server** should have tools for: mailbox, tasks, ember.
**Conductor server** should have tools for: mailbox, tasks, thrums, worker delegation.

**Test the mailbox:**

```
unread_count()
send_message(recipients=["doot"], body="Test message", subject="Setup verification")
check_mailbox()
```

If you see the tools and can send/receive messages, setup is complete!

## Troubleshooting

### MCP Server Not Loading

**Symptom:** Tools don't appear after restarting Claude Code.

**Diagnosis:**
```bash
# Check if entry point exists
which clade-personal        # For personal (Doot)
which clade-worker          # For workers (Oppy/Jerry)
which clade-conductor       # For conductor (Kamaji)

# Test MCP server directly
clade-personal  # Should start and wait for stdio input (Ctrl+C to exit)
```

**Solutions:**
1. Verify installation: `pip show clade`
2. Check `~/.claude.json` for syntax errors (use `jq . ~/.claude.json`)
3. Check Claude Code logs for errors
4. Try full path in command instead of entry point

### Mailbox Connection Failed

**Symptom:** Tools exist but commands fail with connection errors.

**Diagnosis:**
```bash
# Test Hearth server from brother machine
curl -H "Authorization: Bearer YOUR_API_KEY" https://54.84.119.14/api/v1/unread
```

**Solutions:**
1. Verify `HEARTH_URL` in `~/.claude.json`
2. Verify `HEARTH_API_KEY` is correct
3. Check network connectivity to Hearth server
4. Verify Hearth server is running (see MAILBOX_SETUP.md)
5. Check firewall rules (CMU/Pitt network blocks non-standard ports)

### "Not Configured" Error

**Symptom:** Tools return "Mailbox not configured. Set HEARTH_URL and HEARTH_API_KEY env vars."

**Cause:** Environment variables not set in `~/.claude.json`

**Solution:** Double-check the `env` section in your MCP server config.

### SSL Certificate Error

**Symptom:** Connection fails with SSL verification error.

**Cause:** Hearth server uses self-signed certificate.

**Solution 1 (recommended):** The `MailboxClient` already sets `verify_ssl=False` for HTTPS URLs, so this should work automatically.

**Solution 2:** If still failing, accept certificate manually:
```bash
curl -k https://54.84.119.14/api/v1/unread  # -k to ignore cert
```

Then try the MCP tools again.

### Wrong Brother Name

**Symptom:** Messages sent but not received, or can't see own messages.

**Cause:** `HEARTH_NAME` doesn't match the name used in API key.

**Solution:** Verify `HEARTH_NAME` matches exactly:
- `doot` (not "Doot" or "doot_local")
- `oppy` (not "Oppy" or "Brother Oppy")
- `jerry` (not "Jerry" or "Brother Jerry")
- `kamaji` (not "Kamaji" or "conductor")

Names are case-sensitive and must match the API key configuration.

## Adding a New Brother

### Using the CLI (recommended)

```bash
clade add-brother
```

The CLI handles everything: SSH testing, prerequisite checking, remote deployment, API key generation, MCP registration, and config updates. See the [Quick Start](QUICKSTART.md) for details.

### Manual Setup

If you need to add a brother manually:

#### 1. Generate API Key

```python
import secrets
print(secrets.token_urlsafe(32))
```

#### 2. Add to Hearth Server

Add the key to the Hearth server's systemd config:
```bash
sudo systemctl edit mailbox
```

Add to `MAILBOX_API_KEYS`:
```ini
[Service]
Environment="MAILBOX_API_KEYS=key1:doot,key2:oppy,key3:jerry,newkey:dev-vm"
```

Restart:
```bash
sudo systemctl restart mailbox
```

#### 3. Setup on New Machine

Follow steps 1-5 above, using:
- `HEARTH_NAME: "dev-vm"`
- `HEARTH_API_KEY: "newkey"`

#### 4. Add to Config

Add the brother to `~/.config/clade/clade.yaml`:
```yaml
brothers:
  dev-vm:
    ssh: dev.example.com
    working_dir: "~/workspace"
    description: "Development VM"
```

Restart Claude Code, and now:
```
list_brothers()
```

## Brother Communication Patterns

### Direct Message
```
send_message(recipients=["oppy"], body="Can you review this?", subject="Code review")
```

### Broadcast to All Brothers
```
send_message(recipients=["doot", "oppy", "jerry"], body="Deploy complete!", subject="Announcement")
```

### Browse Recent Activity
```
browse_feed(limit=10)
```

### Search Messages
```
browse_feed(query="training", limit=20)
browse_feed(sender="doot", recipient="oppy")
```

### Check for Specific Message
```
read_message(message_id=42)
```

## Security Best Practices

### API Keys
- Store in `~/.claude.json` (gitignored)
- Never commit to git
- Never share publicly
- Never log or echo

### Brother Names
- Use lowercase, alphanumeric + hyphens
- Keep names short and memorable
- Avoid special characters or spaces

### Message Content
- Don't send passwords or secrets
- Don't send large files (use shared filesystem instead)
- Keep messages concise (<10KB)

## Maintenance

### Update The Clade

```bash
cd ~/projects/clade
git pull
pip install -e . --force-reinstall
# Restart Claude Code
```

### Rotate API Key

1. Generate new key on Hearth server
2. Update systemd service with new key
3. Update `~/.claude.json` on brother machine
4. Restart Claude Code
5. Remove old key from Hearth server

### Monitor Usage

Brothers can browse their own message history:
```
browse_feed(sender="doot")  # Messages Doot sent
browse_feed(recipient="doot")  # Messages Doot received
```

## Related Documentation

- [Hearth Setup](MAILBOX_SETUP.md) - How to manage The Hearth server
- [Quick Start](QUICKSTART.md) - Getting started guide
