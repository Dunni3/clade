"""clade setup-ember — set up an Ember server on an existing brother."""

from __future__ import annotations

import click

from .clade_config import default_config_path, load_clade_config, save_clade_config
from .ember_setup import setup_ember
from .keys import keys_path, load_keys


@click.command()
@click.argument("name")
@click.option("--port", default=8100, type=int, help="Ember server port (default: 8100)")
@click.option("--yes", "-y", is_flag=True, help="Accept defaults without prompting")
@click.pass_context
def setup_ember_cmd(ctx: click.Context, name: str, port: int, yes: bool) -> None:
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
