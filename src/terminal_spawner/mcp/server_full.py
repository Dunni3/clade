"""Full MCP server for Doot with terminal spawning, mailbox, and task tools."""
import os

from mcp.server.fastmcp import FastMCP

from ..communication.mailbox_client import MailboxClient
from ..core.config import load_config
from .tools.mailbox_tools import create_mailbox_tools
from .tools.task_tools import create_task_tools
from .tools.terminal_tools import create_terminal_tools

# Load configuration
config = load_config()

# Initialize MCP server
mcp = FastMCP("terminal-spawner")

# Register terminal tools
create_terminal_tools(mcp, config)

# Setup mailbox client if configured
_mailbox_url = os.environ.get("MAILBOX_URL")
_mailbox_api_key = os.environ.get("MAILBOX_API_KEY")
_mailbox_name = os.environ.get("MAILBOX_NAME")

_mailbox: MailboxClient | None = None
if _mailbox_url and _mailbox_api_key:
    _verify_ssl = False  # self-signed cert on our EC2 instance
    _mailbox = MailboxClient(_mailbox_url, _mailbox_api_key, verify_ssl=_verify_ssl)

# Register mailbox tools
create_mailbox_tools(mcp, _mailbox)

# Register task delegation tools (pass URL/key for hook-based task logging)
create_task_tools(mcp, _mailbox, config, mailbox_url=_mailbox_url, mailbox_api_key=_mailbox_api_key)


def main():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
