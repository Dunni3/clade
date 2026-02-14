"""clade init — interactive setup wizard for a new Clade."""

from __future__ import annotations

import sys

import click

from .clade_config import CladeConfig, default_config_path, save_clade_config
from .identity import generate_personal_identity, write_identity_local
from .keys import add_key, keys_path
from .mcp_utils import is_mcp_registered, register_mcp_server
from .naming import format_suggestion, suggest_name


@click.command()
@click.option("--name", "clade_name", default=None, help="Clade name")
@click.option("--personal-name", default=None, help="Your personal brother name")
@click.option("--personal-desc", default=None, help="Your personal brother description")
@click.option("--personality", default=None, help="Personality description for your personal brother")
@click.option("--server-url", default=None, help="Hearth server URL")
@click.option("--server-ssh", default=None, help="Hearth server SSH (e.g. ubuntu@host)")
@click.option("--server-ssh-key", default=None, help="SSH key for the server")
@click.option("--no-mcp", is_flag=True, help="Skip MCP registration in ~/.claude.json")
@click.option("--no-identity", is_flag=True, help="Skip writing identity to CLAUDE.md")
@click.option("--yes", "-y", is_flag=True, help="Accept defaults without prompting")
@click.pass_context
def init_cmd(
    ctx: click.Context,
    clade_name: str | None,
    personal_name: str | None,
    personal_desc: str | None,
    personality: str | None,
    server_url: str | None,
    server_ssh: str | None,
    server_ssh_key: str | None,
    no_mcp: bool,
    no_identity: bool,
    yes: bool,
) -> None:
    """Initialize a new Clade configuration."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    config_path = default_config_path(config_dir)

    # Check for existing config
    if config_path.exists():
        if not yes:
            click.confirm(
                f"Config already exists at {config_path}. Overwrite?",
                abort=True,
            )

    # Clade name
    if clade_name is None:
        if yes:
            clade_name = "My Clade"
        else:
            clade_name = click.prompt("Clade name", default="My Clade")

    # Personal brother name
    if personal_name is None:
        suggestion = suggest_name()
        if yes:
            personal_name = suggestion["name"]
        else:
            click.echo(f"  Suggestion: {format_suggestion(suggestion)}")
            personal_name = click.prompt(
                "Your personal brother name",
                default=suggestion["name"],
            )

    # Personal description
    if personal_desc is None:
        if yes:
            personal_desc = "Personal assistant and coordinator"
        else:
            personal_desc = click.prompt(
                "Description",
                default="Personal assistant and coordinator",
            )

    # Personality
    if personality is None and not yes:
        click.echo()
        click.echo("Personality gives your Claude Code instance a distinct character.")
        click.echo('Example: "Methodical and detail-oriented. Loves clean architecture."')
        personality = click.prompt("Personality (optional, Enter to skip)", default="")
    personality = personality or ""

    # Server configuration
    if not yes and server_url is None:
        if click.confirm("Configure a Hearth server now?", default=False):
            server_url = click.prompt("Server URL (e.g. https://your-server.com)")
            server_ssh = click.prompt("Server SSH (e.g. ubuntu@your-server.com)", default="")
            server_ssh_key = click.prompt("SSH key path (optional)", default="")
            if not server_ssh:
                server_ssh = None
            if not server_ssh_key:
                server_ssh_key = None

    # Build config
    config = CladeConfig(
        clade_name=clade_name,
        personal_name=personal_name,
        personal_description=personal_desc,
        personal_personality=personality,
        server_url=server_url,
        server_ssh=server_ssh,
        server_ssh_key=server_ssh_key,
    )

    # Save config
    save_clade_config(config, config_path)
    click.echo(f"Config written to {config_path}")

    # Generate API key for personal brother
    kp = keys_path(config_dir)
    key = add_key(personal_name, kp)
    click.echo(f"API key for '{personal_name}' saved to {kp}")

    # Register MCP server
    if not no_mcp:
        _register_personal_mcp(personal_name, key, server_url)

    # Write identity to CLAUDE.md
    if not no_identity:
        identity = generate_personal_identity(
            name=personal_name,
            clade_name=clade_name,
            personality=personality,
        )
        claude_md_path = (config_dir / "CLAUDE.md") if config_dir else None
        identity_path = write_identity_local(identity, claude_md_path)
        click.echo(f"Identity written to {identity_path}")

    # Next steps
    click.echo()
    click.echo(click.style("Next steps:", bold=True))
    click.echo("  1. Restart Claude Code to pick up the new config")
    click.echo("  2. Add brothers with: clade add-brother")
    if not server_url:
        click.echo("  3. Set up a Hearth server for inter-brother communication")


def _register_personal_mcp(
    name: str,
    api_key: str,
    server_url: str | None,
) -> None:
    """Register the personal MCP server in ~/.claude.json."""
    server_name = "clade-personal"
    if is_mcp_registered(server_name):
        click.echo(f"MCP server '{server_name}' already registered in ~/.claude.json")
        return

    python_path = sys.executable
    env: dict[str, str] = {}
    if server_url:
        env["HEARTH_URL"] = server_url
        env["HEARTH_API_KEY"] = api_key
        env["HEARTH_NAME"] = name

    register_mcp_server(
        server_name,
        python_path,
        "clade.mcp.server_full",
        env=env if env else None,
    )
    click.echo(f"Registered '{server_name}' MCP server in ~/.claude.json")
