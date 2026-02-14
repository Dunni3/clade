"""Clade CLI entry point."""

import click

from .init_cmd import init_cmd
from .add_brother import add_brother
from .status_cmd import status_cmd
from .doctor import doctor


@click.group()
@click.version_option(package_name="clade")
def cli():
    """The Clade — setup and manage your family of Claude Code instances."""


cli.add_command(init_cmd, "init")
cli.add_command(add_brother, "add-brother")
cli.add_command(status_cmd, "status")
cli.add_command(doctor, "doctor")
