"""clade setup-gh-auth — set up gh CLI authentication on a brother's remote machine."""

from __future__ import annotations

import click

from .clade_config import default_config_path, load_clade_config
from .ssh_utils import run_remote


@click.command()
@click.argument("brother")
@click.pass_context
def setup_gh_auth_cmd(ctx: click.Context, brother: str) -> None:
    """Set up gh CLI authentication on a brother's remote machine."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None

    # Load config
    config = load_clade_config(default_config_path(config_dir))
    if config is None:
        click.echo(click.style("No clade.yaml found. Run 'clade init' first.", fg="red"), err=True)
        raise SystemExit(1)

    if brother not in config.brothers:
        known = ", ".join(sorted(config.brothers.keys())) or "(none)"
        click.echo(
            click.style(f"Unknown brother '{brother}'. Known: {known}", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    bro = config.brothers[brother]
    ssh_host = bro.ssh
    ssh_key = config.server_ssh_key

    # Check if gh is installed
    click.echo(f"Checking gh CLI on {ssh_host}...")
    check_result = run_remote(ssh_host, "command -v gh && echo GH_FOUND || echo GH_MISSING", ssh_key=ssh_key)

    if not check_result.success:
        click.echo(click.style(f"SSH to {ssh_host} failed: {check_result.message}", fg="red"), err=True)
        raise SystemExit(1)

    gh_installed = "GH_FOUND" in check_result.stdout

    # Check if already authenticated
    if gh_installed:
        auth_result = run_remote(ssh_host, "gh auth status 2>&1 && echo GH_AUTHED || echo GH_NOT_AUTHED", ssh_key=ssh_key)
        if "GH_AUTHED" in auth_result.stdout:
            click.echo(click.style("gh CLI is already authenticated.", fg="green"))
            # Show status details
            for line in auth_result.stdout.strip().splitlines():
                if line.strip() and line.strip() != "GH_AUTHED":
                    click.echo(f"  {line.strip()}")
            return

    # Install gh if needed
    if not gh_installed:
        click.echo(f"Installing gh CLI on {ssh_host}...")
        install_script = """\
#!/bin/bash
set -e
if command -v apt-get &>/dev/null; then
    # Debian/Ubuntu
    (type -p wget >/dev/null || (sudo apt update && sudo apt-get install wget -y))
    sudo mkdir -p -m 755 /etc/apt/keyrings
    out=$(wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg) && echo "$out" | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
    sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    sudo apt update && sudo apt install gh -y
elif command -v dnf &>/dev/null; then
    sudo dnf install -y gh
elif command -v yum &>/dev/null; then
    sudo yum install -y gh
elif command -v brew &>/dev/null; then
    brew install gh
elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm github-cli
else
    echo "INSTALL_FAILED: no supported package manager found" >&2
    exit 1
fi
echo "GH_INSTALL_OK"
"""
        install_result = run_remote(ssh_host, install_script, ssh_key=ssh_key, timeout=120)
        if not install_result.success or "GH_INSTALL_OK" not in install_result.stdout:
            click.echo(click.style(f"Failed to install gh CLI: {install_result.message}", fg="red"), err=True)
            if install_result.stderr:
                click.echo(f"  stderr: {install_result.stderr[:300]}")
            raise SystemExit(1)
        click.echo(click.style("  gh CLI installed", fg="green"))

    # Prompt for PAT
    click.echo()
    click.echo("A GitHub Personal Access Token (PAT) is needed to authenticate.")
    click.echo("Create one at: https://github.com/settings/tokens")
    pat = click.prompt("GitHub PAT", hide_input=True)
    if not pat or not pat.strip():
        click.echo(click.style("Empty token provided.", fg="red"), err=True)
        raise SystemExit(1)

    # Authenticate via heredoc (avoids shell injection)
    click.echo(f"Authenticating gh on {ssh_host}...")
    auth_script = f"""\
#!/bin/bash
set -e
gh auth login --with-token << 'CLADETOKEN'
{pat.strip()}
CLADETOKEN
echo "GH_AUTH_OK"
"""
    auth_result = run_remote(ssh_host, auth_script, ssh_key=ssh_key, timeout=30)
    if not auth_result.success or "GH_AUTH_OK" not in auth_result.stdout:
        click.echo(click.style(f"Authentication failed: {auth_result.message}", fg="red"), err=True)
        if auth_result.stderr:
            click.echo(f"  stderr: {auth_result.stderr[:300]}")
        raise SystemExit(1)

    # Verify
    verify_result = run_remote(ssh_host, "gh auth status 2>&1", ssh_key=ssh_key)
    click.echo(click.style("gh CLI authenticated successfully!", fg="green"))
    for line in verify_result.stdout.strip().splitlines():
        if line.strip():
            click.echo(f"  {line.strip()}")
