"""Ember server MCP tool definitions."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ...worker.client import EmberClient


_NOT_CONFIGURED = "Ember not configured. Set EMBER_URL and EMBER_API_KEY env vars."


def create_ember_tools(
    mcp: FastMCP,
    ember: EmberClient | None,
    brothers_registry: dict[str, dict] | None = None,
    registry_loader: Callable[[], dict[str, dict]] | None = None,
) -> dict:
    """Register Ember tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        ember: EmberClient instance, or None if not configured (for local/default Ember)
        brothers_registry: Static dict of brother configs (deprecated, use registry_loader)
        registry_loader: Callable that returns fresh registry on each call

    Returns:
        Dict mapping tool names to their callable functions (for testing).
    """

    def _get_registry() -> dict[str, dict]:
        if registry_loader is not None:
            return registry_loader()
        return brothers_registry or {}

    def _get_ember_client(brother: str) -> EmberClient | None:
        registry = _get_registry()
        config = registry.get(brother)
        if not config:
            return None
        url = config.get("ember_url")
        key = config.get("ember_api_key") or config.get("api_key")
        if not url or not key:
            return None
        return EmberClient(url, key, verify_ssl=False)

    @mcp.tool()
    async def check_ember_health(
        brother: str | None = None,
        url: str | None = None,
    ) -> str:
        """Check the health of an Ember server.

        Args:
            brother: Brother name to check (e.g. "oppy"). If not provided and no url,
                     checks all brothers in the registry, falling back to the configured Ember.
            url: Optional URL override for ad-hoc checks (e.g. "http://100.71.57.52:8100").
        """
        # Ad-hoc URL check
        if url:
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

        # Named brother check
        if brother:
            reg = _get_registry()
            if brother not in reg:
                return f"Unknown brother '{brother}'."
            client = _get_ember_client(brother)
            if client is None:
                return f"{brother}: No Ember configured"
            try:
                result = await client.health()
                return (
                    f"{brother}: Healthy\n"
                    f"  Active tasks: {result.get('active_tasks', '?')}\n"
                    f"  Uptime: {result.get('uptime_seconds', '?')}s"
                )
            except Exception as e:
                return f"{brother}: Unreachable ({e})"

        # No brother specified — check all in registry, or fall back to configured Ember
        reg = _get_registry()
        if reg:
            lines = []
            for name in reg:
                client = _get_ember_client(name)
                if client is None:
                    lines.append(f"{name}: No Ember configured")
                    continue
                try:
                    result = await client.health()
                    lines.append(
                        f"{name}: Healthy\n"
                        f"  Active tasks: {result.get('active_tasks', '?')}\n"
                        f"  Uptime: {result.get('uptime_seconds', '?')}s"
                    )
                except Exception as e:
                    lines.append(f"{name}: Unreachable ({e})")
            return "\n\n".join(lines)

        # Fall back to configured Ember
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
    async def list_ember_tasks(brother: str | None = None) -> str:
        """List active tasks and orphaned tmux sessions on Ember servers.

        Args:
            brother: Brother name to check (e.g. "oppy"). If not provided,
                     checks all brothers in the registry, falling back to the configured Ember.
        """
        # Named brother check
        if brother:
            reg = _get_registry()
            if brother not in reg:
                return f"Unknown brother '{brother}'."
            client = _get_ember_client(brother)
            if client is None:
                return f"{brother}: No Ember configured"
            try:
                result = await client.active_tasks()
                return _format_active_tasks(brother, result)
            except Exception as e:
                return f"{brother}: Unreachable ({e})"

        # No brother specified — check all in registry, or fall back to configured Ember
        reg = _get_registry()
        if reg:
            lines = []
            for name in reg:
                client = _get_ember_client(name)
                if client is None:
                    lines.append(f"{name}: No Ember configured")
                    continue
                try:
                    result = await client.active_tasks()
                    lines.append(_format_active_tasks(name, result))
                except Exception as e:
                    lines.append(f"{name}: Unreachable ({e})")
            return "\n\n".join(lines)

        # Fall back to configured Ember
        if ember is None:
            return _NOT_CONFIGURED
        try:
            result = await ember.active_tasks()
            return _format_active_tasks(None, result)
        except Exception as e:
            return f"Error listing Ember tasks: {e}"

    return {
        "check_ember_health": check_ember_health,
        "list_ember_tasks": list_ember_tasks,
    }


def _format_active_tasks(label: str | None, result: dict) -> str:
    """Format active tasks response from an Ember server."""
    lines = []

    aspens = result.get("aspens")
    if aspens is None:
        active = result.get("active_task")
        aspens = [active] if active else []

    prefix = f"{label}: " if label else ""

    if aspens:
        n = len(aspens)
        lines.append(f"{prefix}{n} active aspen{'s' if n != 1 else ''}")
        for a in aspens:
            lines.append(
                f"  - Task ID: {a.get('task_id', 'N/A')}\n"
                f"    Session: {a.get('session_name', '?')}\n"
                f"    Subject: {a.get('subject', '(none)')}\n"
                f"    Working dir: {a.get('working_dir', 'N/A')}\n"
                f"    Alive: {a.get('alive', '?')}"
            )
    else:
        lines.append(f"{prefix}Idle" if label else "No active aspens.")

    orphaned = result.get("orphaned_sessions", [])
    if orphaned:
        lines.append(f"\nOrphaned tmux sessions ({len(orphaned)}):")
        for s in orphaned:
            lines.append(f"  - {s}")

    return "\n".join(lines)
