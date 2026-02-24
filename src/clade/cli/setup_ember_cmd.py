"""clade setup-ember — set up an Ember server on an existing brother."""

from __future__ import annotations

import click

from .clade_config import default_config_path, load_clade_config, save_clade_config
from .ember_setup import (
    detect_remote_user,
    detect_systemctl_path,
    generate_sudoers_command,
    install_sudoers_remote,
    setup_ember,
    verify_sudoers_remote,
)
from .keys import keys_path, load_keys


@click.command()
@click.argument("name")
@click.option("--port", default=8100, type=int, help="Ember server port (default: 8100)")
@click.option("--sudoers", "setup_sudoers", is_flag=True, help="Set up passwordless sudo for Ember service restarts")
@click.option("--yes", "-y", is_flag=True, help="Accept defaults without prompting")
@click.pass_context
def setup_ember_cmd(ctx: click.Context, name: str, port: int, setup_sudoers: bool, yes: bool) -> None:
    """Set up an Ember server on an existing brother.

    NAME is the brother's name (must already exist in clade.yaml).
    """
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None

    # Load config
    config_path = default_config_path(config_dir)
    config = load_clade_config(config_path)
    if config is None:
        click.echo("No clade.yaml found. Run 'clade init' first.", err=True)
        raise SystemExit(1)

    if name not in config.brothers:
        click.echo(f"Brother '{name}' not found in config.", err=True)
        click.echo(f"Known brothers: {', '.join(config.brothers.keys()) or '(none)'}", err=True)
        raise SystemExit(1)

    bro = config.brothers[name]

    # Load API key
    kp = keys_path(config_dir)
    keys = load_keys(kp)
    api_key = keys.get(name)
    if not api_key:
        click.echo(f"No API key found for '{name}' in {kp}", err=True)
        click.echo("Run 'clade add-brother' to generate one.", err=True)
        raise SystemExit(1)

    # Load caller's API key for Hearth registration
    caller_key = keys.get(config.personal_name) or api_key

    # Run setup
    ember_host, ember_port = setup_ember(
        ssh_host=bro.ssh,
        name=name,
        api_key=api_key,
        port=port,
        working_dir=bro.working_dir,
        server_url=config.server_url,
        yes=yes,
        hearth_api_key=caller_key,
        verify_ssl=config.verify_ssl,
    )

    # Update config
    if ember_host:
        bro.ember_host = ember_host
        bro.ember_port = ember_port
        save_clade_config(config, config_path)
        click.echo(f"\nEmber config saved: {ember_host}:{ember_port}")
    else:
        click.echo("\nEmber setup did not complete. Config not updated.")

    # Sudoers setup
    if setup_sudoers:
        _setup_sudoers(bro.ssh, name, config, config_path, config_dir)


def _setup_sudoers(
    ssh_host: str,
    name: str,
    config,
    config_path,
    config_dir,
) -> None:
    """Set up passwordless sudo for Ember service restarts."""
    click.echo()
    click.echo(click.style("Setting up passwordless sudo for Ember restarts...", bold=True))

    # Detect remote user
    remote_user = detect_remote_user(ssh_host)
    if not remote_user:
        click.echo(click.style("  Could not detect remote user", fg="red"))
        return

    # Detect systemctl path
    systemctl_path = detect_systemctl_path(ssh_host)
    if not systemctl_path:
        click.echo(click.style("  Could not detect systemctl path on remote", fg="red"))
        return

    click.echo(f"  User: {remote_user}")
    click.echo(f"  systemctl: {systemctl_path}")

    # Show the command for the user
    cmd = generate_sudoers_command(ssh_host, remote_user, systemctl_path)
    click.echo()
    click.echo("  The following command will install a scoped sudoers rule:")
    click.echo()
    click.echo(f"    {cmd}")
    click.echo()

    # Ask for confirmation
    if not click.confirm("  Install this sudoers rule now?", default=True):
        click.echo("  Skipped. You can run the command above manually.")
        return

    # Install
    result = install_sudoers_remote(ssh_host, remote_user, systemctl_path)
    if not result.success or "SUDOERS_OK" not in result.stdout:
        click.echo(click.style("  Failed to install sudoers rule", fg="red"))
        if result.stderr:
            click.echo(f"  Error: {result.stderr[:200]}")
        click.echo("  You can run the command above manually instead.")
        return

    click.echo(click.style("  Sudoers rule installed", fg="green"))

    # Verify
    click.echo("  Verifying passwordless sudo...")
    if verify_sudoers_remote(ssh_host, systemctl_path):
        click.echo(click.style("  Verification passed!", fg="green"))
        config.brothers[name].sudoers_configured = True
        save_clade_config(config, config_path)
        click.echo("  Saved sudoers_configured=true to clade.yaml")
    else:
        click.echo(click.style("  Verification failed — sudo may still require a password", fg="yellow"))
        click.echo("  Try running the command above manually with 'ssh -t'.")
