"""clade add-brother — add and configure a new brother."""

from __future__ import annotations

import click

from .clade_config import (
    BrotherEntry,
    default_config_path,
    load_clade_config,
    save_clade_config,
)
from .identity import generate_worker_identity, write_identity_remote
from .keys import add_key, keys_path
from .mcp_utils import register_mcp_remote
from .naming import format_suggestion, suggest_name
from .ssh_utils import check_remote_prereqs, run_remote, test_ssh


@click.command()
@click.option("--name", default=None, help="Brother name")
@click.option("--ssh", "ssh_host", default=None, help="SSH host (e.g. ian@masuda)")
@click.option("--working-dir", default=None, help="Working directory on remote host")
@click.option("--role", default="worker", help="Role (worker/general)")
@click.option("--description", "desc", default=None, help="Description")
@click.option("--personality", default=None, help="Personality description for the brother")
@click.option("--no-deploy", is_flag=True, help="Skip deploying the clade package on remote")
@click.option("--no-mcp", is_flag=True, help="Skip MCP registration on remote")
@click.option("--no-identity", is_flag=True, help="Skip writing identity to remote CLAUDE.md")
@click.option("--yes", "-y", is_flag=True, help="Accept defaults without prompting")
@click.pass_context
def add_brother(
    ctx: click.Context,
    name: str | None,
    ssh_host: str | None,
    working_dir: str | None,
    role: str,
    desc: str | None,
    personality: str | None,
    no_deploy: bool,
    no_mcp: bool,
    no_identity: bool,
    yes: bool,
) -> None:
    """Add a new brother to the Clade."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None

    # Load existing config
    config = load_clade_config(default_config_path(config_dir))
    if config is None:
        click.echo("No clade.yaml found. Run 'clade init' first.", err=True)
        raise SystemExit(1)

    used_names = list(config.brothers.keys()) + [config.personal_name]

    # Brother name
    if name is None:
        suggestion = suggest_name(used_names)
        if yes:
            name = suggestion["name"]
        else:
            click.echo(f"  Suggestion: {format_suggestion(suggestion)}")
            name = click.prompt("Brother name", default=suggestion["name"])

    if name in config.brothers:
        click.echo(f"Brother '{name}' already exists in config.", err=True)
        raise SystemExit(1)

    # SSH host
    if ssh_host is None:
        ssh_host = click.prompt("SSH host (e.g. ian@masuda)")

    # Test SSH
    click.echo(f"Testing SSH to {ssh_host}...")
    ssh_result = test_ssh(ssh_host)
    if not ssh_result.success:
        click.echo(f"SSH failed: {ssh_result.message}", err=True)
        if not yes and not click.confirm("Continue anyway?", default=False):
            raise SystemExit(1)
    else:
        click.echo(click.style("  SSH OK", fg="green"))

    # Check prerequisites
    if ssh_result.success:
        click.echo("Checking remote prerequisites...")
        prereqs = check_remote_prereqs(ssh_host)
        for attr, label in [("python", "Python 3.10+"), ("claude", "Claude Code"), ("tmux", "tmux"), ("git", "git")]:
            val = getattr(prereqs, attr)
            if attr == "python":
                if val:
                    click.echo(click.style(f"  {label}: {prereqs.python_version}", fg="green"))
                else:
                    click.echo(click.style(f"  {label}: NOT FOUND", fg="red"))
            else:
                if val:
                    click.echo(click.style(f"  {label}: OK", fg="green"))
                else:
                    click.echo(click.style(f"  {label}: NOT FOUND", fg="red"))

        if prereqs.errors and not yes:
            click.echo(f"Missing: {', '.join(prereqs.errors)}")
            if not click.confirm("Continue anyway?", default=False):
                raise SystemExit(1)

    # Working directory
    if working_dir is None:
        if yes:
            working_dir = "~"
        else:
            working_dir = click.prompt("Working directory on remote", default="~")
    if working_dir == "~":
        working_dir = None  # None means home directory (no cd)

    # Description
    if desc is None:
        if yes:
            desc = f"Brother {name}"
        else:
            desc = click.prompt("Description", default=f"Brother {name}")

    # Personality
    if personality is None and not yes:
        click.echo()
        click.echo("Personality gives this brother a distinct character.")
        click.echo('Example: "Intellectual and curious. Loves clean, scalable systems."')
        personality = click.prompt("Personality (optional, Enter to skip)", default="")
    personality = personality or ""

    # Deploy clade package on remote
    if not no_deploy and ssh_result.success:
        _deploy_remote(ssh_host, name)

    # Generate API key
    kp = keys_path(config_dir)
    api_key = add_key(name, kp)
    click.echo(f"API key for '{name}' saved to {kp}")

    # Register MCP on remote
    if not no_mcp and ssh_result.success:
        _register_remote_mcp(ssh_host, name, api_key, config.server_url)

    # Write identity to remote CLAUDE.md
    if not no_identity and ssh_result.success:
        _write_remote_identity(
            ssh_host=ssh_host,
            name=name,
            clade_name=config.clade_name,
            personality=personality,
            role=role,
            personal_name=config.personal_name,
            brothers=config.brothers,
        )

    # Update config
    config.brothers[name] = BrotherEntry(
        ssh=ssh_host,
        working_dir=working_dir,
        role=role,
        description=desc,
        personality=personality,
    )
    config_path = default_config_path(config_dir)
    save_clade_config(config, config_path)
    click.echo(f"Brother '{name}' added to {config_path}")

    # Summary
    click.echo()
    click.echo(click.style("Summary:", bold=True))
    click.echo(f"  Name: {name}")
    click.echo(f"  SSH:  {ssh_host}")
    if working_dir:
        click.echo(f"  Dir:  {working_dir}")
    click.echo(f"  Role: {role}")

    if not config.server_url:
        click.echo()
        click.echo(
            click.style("Note:", bold=True)
            + " No Hearth server configured. Brothers won't be able to communicate"
            + " until you set one up."
        )


def _deploy_remote(ssh_host: str, name: str) -> None:
    """Clone/pull the clade repo and install on the remote host."""
    click.echo(f"Deploying clade package on {ssh_host}...")
    script = """\
#!/bin/bash
set -e
CLADE_DIR="$HOME/.local/share/clade"
if [ -d "$CLADE_DIR/.git" ]; then
    cd "$CLADE_DIR"
    git pull --ff-only 2>&1
else
    git clone https://github.com/dunni3/clade.git "$CLADE_DIR" 2>&1
fi
cd "$CLADE_DIR"
pip install -e . 2>&1 | tail -3
echo "DEPLOY_OK"
"""
    result = run_remote(ssh_host, script, timeout=120)
    if result.success and "DEPLOY_OK" in result.stdout:
        click.echo(click.style("  Deploy OK", fg="green"))
    else:
        click.echo(click.style(f"  Deploy failed: {result.message}", fg="red"))
        if result.stderr:
            click.echo(f"  stderr: {result.stderr[:200]}")


def _register_remote_mcp(
    ssh_host: str,
    name: str,
    api_key: str,
    server_url: str | None,
) -> None:
    """Register the clade-worker MCP server on the remote host."""
    if not server_url:
        click.echo("  Skipping remote MCP registration (no server URL configured)")
        return

    click.echo(f"Registering MCP on {ssh_host}...")
    env = {
        "HEARTH_URL": server_url,
        "HEARTH_API_KEY": api_key,
        "HEARTH_NAME": name,
    }
    result = register_mcp_remote(
        ssh_host,
        "clade-worker",
        "python3",
        "clade.mcp.server_lite",
        env,
    )
    if result.success and "MCP_REGISTERED" in result.stdout:
        click.echo(click.style("  MCP registered", fg="green"))
    else:
        click.echo(click.style(f"  MCP registration failed: {result.message}", fg="red"))


def _write_remote_identity(
    ssh_host: str,
    name: str,
    clade_name: str,
    personality: str,
    role: str,
    personal_name: str,
    brothers: dict,
) -> None:
    """Write identity section to the remote brother's CLAUDE.md."""
    # Build brothers info dict for the identity generator
    brothers_info = {}
    for bro_name, bro in brothers.items():
        brothers_info[bro_name] = {
            "role": bro.role,
            "description": bro.description,
        }

    identity = generate_worker_identity(
        name=name,
        clade_name=clade_name,
        personality=personality,
        role=role,
        personal_name=personal_name,
        brothers=brothers_info,
    )

    click.echo(f"Writing identity to {ssh_host}...")
    result = write_identity_remote(ssh_host, identity)
    if result.success and "IDENTITY_OK" in result.stdout:
        click.echo(click.style("  Identity written", fg="green"))
    else:
        click.echo(click.style(f"  Identity write failed: {result.message}", fg="red"))
