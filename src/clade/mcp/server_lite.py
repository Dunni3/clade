"""Worker Brother MCP server — for remote brothers (Oppy/Jerry).

Only exposes mailbox tools — no terminal spawning (that's Doot's job).
Requires env vars: HEARTH_URL, HEARTH_API_KEY, HEARTH_NAME (or legacy MAILBOX_* equivalents).
"""

import os

import yaml
from mcp.server.fastmcp import FastMCP

from ..cli.clade_config import load_brothers_registry
from ..communication.mailbox_client import MailboxClient
from ..worker.client import EmberClient
from .tools.delegation_tools import create_delegation_tools
from .tools.ember_tools import create_ember_tools
from .tools.kanban_tools import create_kanban_tools
from .tools.mailbox_tools import create_mailbox_tools

# Initialize MCP server
mcp = FastMCP("clade-worker")

# Setup Hearth client if configured (HEARTH_* with MAILBOX_* fallback)
_hearth_url = os.environ.get("HEARTH_URL") or os.environ.get("MAILBOX_URL")
_hearth_api_key = os.environ.get("HEARTH_API_KEY") or os.environ.get("MAILBOX_API_KEY")
_hearth_name = os.environ.get("HEARTH_NAME") or os.environ.get("MAILBOX_NAME")

_mailbox: MailboxClient | None = None
if _hearth_url and _hearth_api_key:
    _verify_ssl = False  # self-signed cert on our EC2 instance
    _mailbox = MailboxClient(_hearth_url, _hearth_api_key, verify_ssl=_verify_ssl)

# Register mailbox tools
create_mailbox_tools(mcp, _mailbox)

# Register kanban tools
create_kanban_tools(mcp, _mailbox)

# Setup Ember client if configured (worker talks to its own local Ember using its Hearth key)
_ember_url = os.environ.get("EMBER_URL")
_ember = EmberClient(_ember_url, _hearth_api_key, verify_ssl=False) if _ember_url and _hearth_api_key else None

# Build brothers registry: prefer clade.yaml + keys.json (always fresh),
# fall back to BROTHERS_CONFIG file (for backward compat / deployed workers)
_brothers_registry = load_brothers_registry()
if not _brothers_registry:
    _brothers_config_path = os.environ.get("BROTHERS_CONFIG")
    if _brothers_config_path and os.path.exists(_brothers_config_path):
        with open(_brothers_config_path) as f:
            _brothers_data = yaml.safe_load(f) or {}
        _brothers_registry = _brothers_data.get("brothers", {})

create_ember_tools(mcp, _ember, brothers_registry=_brothers_registry)
create_delegation_tools(mcp, _mailbox, _brothers_registry, mailbox_name=_hearth_name)


def main():
    """Entry point for the worker MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
