"""Ember server MCP tool definitions."""

from mcp.server.fastmcp import FastMCP

from ...worker.client import EmberClient


_NOT_CONFIGURED = "Ember not configured. Set EMBER_URL and EMBER_API_KEY env vars."


def create_ember_tools(mcp: FastMCP, ember: EmberClient | None) -> dict:
    """Register Ember tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        ember: EmberClient instance, or None if not configured

    Returns:
        Dict mapping tool names to their callable functions (for testing).
    """

    @mcp.tool()
    async def check_ember_health(url: str | None = None) -> str:
        """Check the health of an Ember server.

        Args:
            url: Optional URL override for ad-hoc checks (e.g. "http://100.71.57.52:8100").
                 If not provided, uses the configured Ember.
        """
        if url:
            # Ad-hoc check — /health is unauthenticated, no key needed
            temp_client = EmberClient(url, api_key="", verify_ssl=False)
            try:
                result = await temp_client.health()
                return (
                    f"Ember at {url} is healthy.\n"
                    f"  Brother: {result.get('brother', '?')}\n"
                    f"  Active tasks: {result.get('active_tasks', '?')}\n"
                    f"  Uptime: {result.get('uptime_seconds', '?')}s"
                )
            except Exception as e:
                return f"Ember at {url} is unreachable: {e}"

        if ember is None:
            return _NOT_CONFIGURED
        try:
            result = await ember.health()
            return (
                f"Ember is healthy.\n"
                f"  Brother: {result.get('brother', '?')}\n"
                f"  Active tasks: {result.get('active_tasks', '?')}\n"
                f"  Uptime: {result.get('uptime_seconds', '?')}s"
            )
        except Exception as e:
            return f"Error checking Ember health: {e}"

    @mcp.tool()
    async def list_ember_tasks() -> str:
        """List active tasks and orphaned tmux sessions on the configured Ember."""
        if ember is None:
            return _NOT_CONFIGURED
        try:
            result = await ember.active_tasks()
            lines = []

            active = result.get("active_task")
            if active:
                lines.append(
                    f"Active task:\n"
                    f"  Task ID: {active.get('task_id', 'N/A')}\n"
                    f"  Session: {active.get('session_name', '?')}\n"
                    f"  Subject: {active.get('subject', '(none)')}\n"
                    f"  Working dir: {active.get('working_dir', 'N/A')}\n"
                    f"  Alive: {active.get('alive', '?')}"
                )
            else:
                lines.append("No active task.")

            orphaned = result.get("orphaned_sessions", [])
            if orphaned:
                lines.append(f"\nOrphaned tmux sessions ({len(orphaned)}):")
                for s in orphaned:
                    lines.append(f"  - {s}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error listing Ember tasks: {e}"

    return {
        "check_ember_health": check_ember_health,
        "list_ember_tasks": list_ember_tasks,
    }
