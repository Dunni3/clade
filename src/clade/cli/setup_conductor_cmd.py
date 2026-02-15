"""clade setup-conductor — deploy the Conductor (Kamaji) on the Hearth server."""

from __future__ import annotations

import click

from .clade_config import default_config_path, load_clade_config
from .conductor_setup import deploy_conductor


@click.command()
@click.option("--personality", default=None, help="Personality description for Kamaji")
@click.option("--no-identity", is_flag=True, help="Skip writing identity to remote CLAUDE.md")
@click.option("--yes", "-y", is_flag=True, help="Accept defaults without prompting")
@click.pass_context
def setup_conductor_cmd(
    ctx: click.Context,
    personality: str | None,
    no_identity: bool,
    yes: bool,
) -> None:
    """Deploy the Conductor (Kamaji) on the Hearth server.

    Sets up the systemd timer, config files, and identity for the Conductor
    on the same host as the Hearth server. Requires server.ssh to be
    configured in clade.yaml.

    This command is idempotent — re-run it to update the workers config
    when brothers change.
    """
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None

    # Load config
    config_path = default_config_path(config_dir)
    config = load_clade_config(config_path)
    if config is None:
        click.echo("No clade.yaml found. Run 'clade init' first.", err=True)
        raise SystemExit(1)

    # Check for brothers with Ember
    ember_brothers = [n for n, b in config.brothers.items() if b.ember_host]
    if not ember_brothers:
        click.echo(
            click.style("Warning:", fg="yellow")
            + " No brothers have Ember configured. The Conductor won't have any workers."
        )
        if not yes and not click.confirm("Continue anyway?", default=False):
            raise SystemExit(0)

    click.echo()
    click.echo(click.style("Deploying Conductor (Kamaji)...", bold=True))
    if ember_brothers:
        click.echo(f"  Workers: {', '.join(ember_brothers)}")
    click.echo()

    success = deploy_conductor(
        config=config,
        config_dir=config_dir,
        personality=personality,
        no_identity=no_identity,
        yes=yes,
    )

    if success:
        click.echo()
        click.echo(click.style("Conductor deployed successfully!", fg="green", bold=True))
        click.echo()
        click.echo("The timer will run every 15 minutes. To check status:")
        click.echo(f"  ssh {config.server_ssh} systemctl status conductor-tick.timer")
        click.echo()
        click.echo("To trigger a tick manually:")
        click.echo(f"  ssh {config.server_ssh} sudo systemctl start conductor-tick.service")
    else:
        click.echo()
        click.echo(click.style("Conductor deployment failed.", fg="red"))
        raise SystemExit(1)
