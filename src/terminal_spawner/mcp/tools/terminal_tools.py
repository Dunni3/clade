"""Shared terminal spawning MCP tool definitions."""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from ...core.types import TerminalSpawnerConfig
from ...terminal.applescript import generate_applescript
from ...terminal.executor import run_applescript


def create_terminal_tools(mcp: FastMCP, config: TerminalSpawnerConfig) -> None:
    """Register terminal spawning tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        config: Terminal spawner configuration
    """

    @mcp.tool()
    def spawn_terminal(
        command: str | None = None,
        app: Literal["iterm2", "terminal"] = "terminal",
    ) -> str:
        """Open a new terminal window, optionally running a command in it.

        Args:
            command: Shell command to run in the new window. If omitted, opens an empty window.
            app: Terminal application to use. Defaults to Terminal.app.
        """
        script = generate_applescript(command, app)
        result = run_applescript(script)
        if result != "OK":
            return result
        if command:
            return f"Opened new {app} window and ran: {command}"
        return f"Opened new {app} window"

    # Dynamically create connect_to_brother with available brothers
    brother_names = list(config["brothers"].keys())

    if brother_names:
        # Create a union type from available brother names
        # This allows the tool to work with any configured brothers
        @mcp.tool()
        def connect_to_brother(name: str) -> str:
            """Open a terminal session to one of our brothers (other Claude Code instances).

            Args:
                name: Which brother to connect to.
            """
            brother = config["brothers"].get(name)
            if not brother:
                available = ", ".join(config["brothers"].keys())
                return f"Unknown brother: {name}. Available: {available}"

            script = generate_applescript(brother["command"], "terminal")
            result = run_applescript(script)
            if result != "OK":
                return result
            return f"Opened session with {brother['description']}"

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
