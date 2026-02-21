"""Conductor MCP server — Kamaji's server for orchestrating task trees and delegating tasks."""

import os

import yaml
from mcp.server.fastmcp import FastMCP

from ..communication.mailbox_client import MailboxClient
from .tools.conductor_tools import create_conductor_tools
from .tools.mailbox_tools import create_mailbox_tools

# Initialize MCP server
mcp = FastMCP("clade-conductor")

# Setup Hearth client if configured
_hearth_url = os.environ.get("HEARTH_URL") or os.environ.get("MAILBOX_URL")
_hearth_api_key = os.environ.get("HEARTH_API_KEY") or os.environ.get("MAILBOX_API_KEY")
_hearth_name = os.environ.get("HEARTH_NAME") or os.environ.get("MAILBOX_NAME")

_mailbox: MailboxClient | None = None
if _hearth_url and _hearth_api_key:
    _verify_ssl = False  # self-signed cert on our EC2 instance
    _mailbox = MailboxClient(_hearth_url, _hearth_api_key, verify_ssl=_verify_ssl)

# Register shared mailbox tools
create_mailbox_tools(mcp, _mailbox)

# Load worker registry
_worker_registry: dict[str, dict] = {}

_workers_config_path = os.environ.get("CONDUCTOR_WORKERS_CONFIG")
if _workers_config_path and os.path.exists(_workers_config_path):
    with open(_workers_config_path) as f:
        _workers_data = yaml.safe_load(f) or {}
    _worker_registry = _workers_data.get("workers", {})

# Register conductor tools
create_conductor_tools(
    mcp,
    _mailbox,
    _worker_registry,
    hearth_url=_hearth_url,
    hearth_api_key=_hearth_api_key,
    mailbox_name=_hearth_name,
)


def main():
    """Entry point for the conductor MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
