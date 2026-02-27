"""Personal Brother MCP server — Doot's full server with terminal, mailbox, and task tools."""
import os

import yaml
from mcp.server.fastmcp import FastMCP

from ..cli.clade_config import load_brothers_registry
from ..communication.mailbox_client import MailboxClient
from ..core.config import load_config
from ..worker.client import EmberClient
from .tools.delegation_tools import create_delegation_tools
from .tools.ember_tools import create_ember_tools
from .tools.kanban_tools import create_kanban_tools
from .tools.mailbox_tools import create_mailbox_tools
from .tools.brother_tools import create_brother_tools
from .tools.task_tools import create_task_tools


# Lazy loaders — re-read config on every tool call so clade.yaml edits
# take effect without restarting Claude Code.
def _load_config():
    return load_config()


def _load_brothers_registry():
    registry = load_brothers_registry()
    if not registry:
        config_path = os.environ.get("BROTHERS_CONFIG")
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            registry = data.get("brothers", {})
    return registry


# Initialize MCP server
mcp = FastMCP("clade-personal")

# Register brother listing tools
create_brother_tools(mcp, config_loader=_load_config)

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

# Register task delegation tools (pass URL/key for hook-based task logging)
create_task_tools(mcp, _mailbox, config_loader=_load_config, mailbox_url=_hearth_url, mailbox_api_key=_hearth_api_key)

# Setup Ember client if configured
# Doot uses EMBER_API_KEY (set to the brother's Hearth key) to authenticate to remote Embers
_ember_url = os.environ.get("EMBER_URL")
_ember_api_key = os.environ.get("EMBER_API_KEY")
_ember = EmberClient(_ember_url, _ember_api_key, verify_ssl=False) if _ember_url and _ember_api_key else None

create_ember_tools(mcp, _ember, registry_loader=_load_brothers_registry, mailbox=_mailbox)
create_delegation_tools(mcp, _mailbox, registry_loader=_load_brothers_registry, mailbox_name=_hearth_name)


def main():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
