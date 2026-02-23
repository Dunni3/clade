"""Brother listing MCP tool definition."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ...core.types import TerminalSpawnerConfig


def create_brother_tools(
    mcp: FastMCP,
    config: TerminalSpawnerConfig | None = None,
    config_loader: Callable[[], TerminalSpawnerConfig] | None = None,
) -> None:
    """Register brother listing tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        config: Static configuration (deprecated, use config_loader)
        config_loader: Callable that returns fresh config on each call
    """

    def _get_config() -> TerminalSpawnerConfig:
        if config_loader is not None:
            return config_loader()
        if config is not None:
            return config
        return {"brothers": {}}

    @mcp.tool()
    def list_brothers() -> str:
        """List all available brother instances.

        Returns:
            Formatted list of brother names and descriptions.
        """
        cfg = _get_config()
        if not cfg["brothers"]:
            return "No brothers configured."

        lines = ["Available brothers:"]
        for name, brother in cfg["brothers"].items():
            lines.append(f"  - {name}: {brother['description']}")
        return "\n".join(lines)
