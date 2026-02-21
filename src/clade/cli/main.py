"""Clade CLI entry point."""

from pathlib import Path

import click

from .init_cmd import init_cmd
from .add_brother import add_brother
from .deploy_cmd import deploy
from .setup_ember_cmd import setup_ember_cmd
from .setup_conductor_cmd import setup_conductor_cmd
from .status_cmd import status_cmd
from .doctor import doctor


@click.group()
@click.version_option(package_name="clade")
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override config directory (default: ~/.config/clade)",
)
@click.pass_context
def cli(ctx: click.Context, config_dir: Path | None) -> None:
    """The Clade — setup and manage your family of Claude Code instances."""
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir


cli.add_command(init_cmd, "init")
cli.add_command(add_brother, "add-brother")
cli.add_command(deploy, "deploy")
cli.add_command(setup_ember_cmd, "setup-ember")
cli.add_command(setup_conductor_cmd, "setup-conductor")
cli.add_command(status_cmd, "status")
cli.add_command(doctor, "doctor")
