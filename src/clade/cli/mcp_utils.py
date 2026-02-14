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
    python_path: str,
    module: str,
    env: dict[str, str] | None = None,
    path: Path | None = None,
) -> None:
    """Register an MCP server in ~/.claude.json.

    Args:
        name: Server name (e.g. 'clade-personal').
        python_path: Absolute path to the python interpreter.
        module: Python module to run (e.g. 'clade.mcp.server_full').
        env: Environment variables to set for the server.
        path: Path to claude.json.
    """
    data = read_claude_json(path)
    if "mcpServers" not in data:
        data["mcpServers"] = {}

    server_config: dict = {
        "command": python_path,
        "args": ["-m", module],
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


def register_mcp_remote(
    host: str,
    server_name: str,
    python_path: str,
    module: str,
    env: dict[str, str],
    ssh_key: str | None = None,
) -> SSHResult:
    """Register an MCP server in ~/.claude.json on a remote host via SSH.

    Args:
        host: SSH host string.
        server_name: MCP server name.
        python_path: Remote python path.
        module: Python module to run.
        env: Environment variables for the server.
        ssh_key: Optional SSH key path.

    Returns:
        SSHResult from the remote operation.
    """
    env_json = json.dumps(env)
    script = f"""\
#!/bin/bash
set -e
CLAUDE_JSON="$HOME/.claude.json"

# Read existing or create empty
if [ -f "$CLAUDE_JSON" ]; then
    CONTENT=$(cat "$CLAUDE_JSON")
else
    CONTENT='{{}}'
fi

# Use python to merge the MCP server entry
python3 -c "
import json, sys
data = json.loads('''$CONTENT''')
if 'mcpServers' not in data:
    data['mcpServers'] = {{}}
data['mcpServers']['{server_name}'] = {{
    'command': '{python_path}',
    'args': ['-m', '{module}'],
    'env': json.loads('''{env_json}'''),
}}
with open('$CLAUDE_JSON', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\\n')
print('MCP_REGISTERED')
"
"""
    return run_remote(host, script, ssh_key=ssh_key, timeout=15)
