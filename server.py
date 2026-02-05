from typing import Literal

from mcp.server.fastmcp import FastMCP

from brothers import BROTHERS
from terminal import generate_applescript, run_applescript

mcp = FastMCP("terminal-spawner")


@mcp.tool()
def spawn_terminal(
    command: str | None = None,
    app: Literal["iterm2", "terminal"] = "iterm2",
) -> str:
    """Open a new terminal window, optionally running a command in it.

    Args:
        command: Shell command to run in the new window. If omitted, opens an empty window.
        app: Terminal application to use. Defaults to iTerm2.
    """
    script = generate_applescript(command, app)
    result = run_applescript(script)
    if result != "OK":
        return result
    if command:
        return f"Opened new {app} window and ran: {command}"
    return f"Opened new {app} window"


@mcp.tool()
def connect_to_brother(name: Literal["jerry", "oppy"]) -> str:
    """Open a terminal session to one of our brothers (other Claude Code instances).

    Args:
        name: Which brother to connect to — "jerry" (cluster) or "oppy" (masuda).
    """
    brother = BROTHERS.get(name)
    if not brother:
        return f"Unknown brother: {name}. Available: {', '.join(BROTHERS.keys())}"

    script = generate_applescript(brother["command"], "iterm2")
    result = run_applescript(script)
    if result != "OK":
        return result
    return f"Opened session with {brother['description']}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
