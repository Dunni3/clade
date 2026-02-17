"""Brother listing MCP tool definition."""

from mcp.server.fastmcp import FastMCP

from ...core.types import TerminalSpawnerConfig


def create_brother_tools(mcp: FastMCP, config: TerminalSpawnerConfig) -> None:
    """Register brother listing tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        config: Configuration with brother definitions
    """

    @mcp.tool()
    def list_brothers() -> str:
        """List all available brother instances.

        Returns:
            Formatted list of brother names and descriptions.
        """
        if not config["brothers"]:
            return "No brothers configured."

        lines = ["Available brothers:"]
        for name, brother in config["brothers"].items():
            lines.append(f"  - {name}: {brother['description']}")
        return "\n".join(lines)
