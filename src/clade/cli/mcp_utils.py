"""Utilities for reading and writing ~/.claude.json MCP server registrations."""

from __future__ import annotations

import json
from pathlib import Path

from .ssh_utils import SSHResult, run_remote


def default_claude_json_path() -> Path:
    """Return the default path to ~/.claude.json."""
    return Path.home() / ".claude.json"


def read_claude_json(path: Path | None = None) -> dict:
    """Read and parse ~/.claude.json.

    Args:
        path: Path to claude.json. Uses ~/.claude.json if None.

    Returns:
        Parsed JSON as dict. Empty dict if file doesn't exist or is invalid.
    """
    p = path or default_claude_json_path()
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def write_claude_json(data: dict, path: Path | None = None) -> None:
    """Write data to ~/.claude.json, preserving formatting.

    Args:
        data: The full claude.json content to write.
        path: Path to write to. Uses ~/.claude.json if None.
    """
    p = path or default_claude_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def register_mcp_server(
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    path: Path | None = None,
) -> None:
    """Register an MCP server in ~/.claude.json.

    Uses the console_scripts entry point directly (e.g. 'clade-worker')
    rather than 'python -m module', so the command must be an absolute path
    to the entry point binary.

    Args:
        name: Server name (e.g. 'clade-personal').
        command: Absolute path to the entry point binary.
        args: Command arguments (default: empty list).
        env: Environment variables to set for the server.
        path: Path to claude.json.
    """
    data = read_claude_json(path)
    if "mcpServers" not in data:
        data["mcpServers"] = {}

    server_config: dict = {
        "command": command,
        "args": args if args is not None else [],
    }
    if env:
        server_config["env"] = env

    data["mcpServers"][name] = server_config
    write_claude_json(data, path)


def is_mcp_registered(name: str, path: Path | None = None) -> bool:
    """Check if an MCP server is registered in ~/.claude.json.

    Args:
        name: Server name to check.
        path: Path to claude.json.

    Returns:
        True if the server name exists in mcpServers.
    """
    data = read_claude_json(path)
    return name in data.get("mcpServers", {})


def update_mcp_env(
    server_name: str,
    env_updates: dict[str, str],
    path: Path | None = None,
) -> bool:
    """Merge env vars into an existing MCP server registration.

    Args:
        server_name: MCP server name to update.
        env_updates: Dict of env vars to merge.
        path: Path to claude.json.

    Returns:
        True if the server existed and was updated, False otherwise.
    """
    config = read_claude_json(path)
    servers = config.get("mcpServers", {})
    if server_name not in servers:
        return False
    servers[server_name].setdefault("env", {}).update(env_updates)
    write_claude_json(config, path)
    return True


def update_mcp_env_remote(
    host: str,
    server_name: str,
    env_updates: dict[str, str],
    ssh_key: str | None = None,
) -> SSHResult:
    """Merge env vars into an existing MCP server registration on a remote host.

    Args:
        host: SSH host string.
        server_name: MCP server name to update.
        env_updates: Dict of env vars to merge.
        ssh_key: Optional SSH key path.

    Returns:
        SSHResult from the remote operation.
    """
    env_items = ", ".join(f"'{k}': '{v}'" for k, v in env_updates.items())
    env_literal = f"{{{env_items}}}"
    script = f"""\
#!/bin/bash
set -e
python3 -c "
import json, os, pathlib

claude_json = pathlib.Path(os.path.expanduser('~/.claude.json'))
if not claude_json.exists():
    print('NO_FILE')
    exit(0)

data = json.loads(claude_json.read_text())
servers = data.get('mcpServers', {{}})
if '{server_name}' not in servers:
    print('NOT_FOUND')
    exit(0)

servers['{server_name}'].setdefault('env', {{}}).update({env_literal})
claude_json.write_text(json.dumps(data, indent=2) + '\\n')
print('ENV_UPDATED')
"
"""
    return run_remote(host, script, ssh_key=ssh_key, timeout=15)


def register_mcp_remote(
    host: str,
    server_name: str,
    command: str,
    env: dict[str, str],
    ssh_key: str | None = None,
) -> SSHResult:
    """Register an MCP server in ~/.claude.json on a remote host via SSH.

    Uses the console_scripts entry point directly (e.g. '/path/to/clade-worker')
    rather than 'python -m module'.

    Args:
        host: SSH host string.
        server_name: MCP server name.
        command: Absolute path to the entry point binary on the remote.
        env: Environment variables for the server.
        ssh_key: Optional SSH key path.

    Returns:
        SSHResult from the remote operation.
    """
    # Build env as a Python dict literal to avoid quoting nightmares
    env_items = ", ".join(f"'{k}': '{v}'" for k, v in env.items())
    env_literal = f"{{{env_items}}}"
    script = f"""\
#!/bin/bash
set -e
python3 -c "
import json, os, pathlib

claude_json = pathlib.Path(os.path.expanduser('~/.claude.json'))
if claude_json.exists():
    data = json.loads(claude_json.read_text())
else:
    data = {{}}

if 'mcpServers' not in data:
    data['mcpServers'] = {{}}

data['mcpServers']['{server_name}'] = {{
    'command': '{command}',
    'args': [],
    'env': {env_literal},
}}

claude_json.write_text(json.dumps(data, indent=2) + '\\n')
print('MCP_REGISTERED')
"
"""
    return run_remote(host, script, ssh_key=ssh_key, timeout=15)
