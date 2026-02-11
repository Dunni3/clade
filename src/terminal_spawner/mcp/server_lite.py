"""Lightweight MCP server for remote brothers (Oppy/Jerry).

Only exposes mailbox tools — no terminal spawning (that's Doot's job).
Requires env vars: MAILBOX_URL, MAILBOX_API_KEY, MAILBOX_NAME.
"""

import os

from mcp.server.fastmcp import FastMCP

from ..communication.mailbox_client import MailboxClient
from .tools.mailbox_tools import create_mailbox_tools

# Initialize MCP server
mcp = FastMCP("brother-mailbox")

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


def main():
    """Entry point for the lite MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
