"""clade status — show Clade health overview."""

from __future__ import annotations

import click
import httpx

from .clade_config import default_config_path, load_clade_config
from .keys import load_keys
from .ssh_utils import test_ssh


@click.command()
def status_cmd() -> None:
    """Show Clade status and health."""
    config = load_clade_config()
    if config is None:
        click.echo("No clade.yaml found. Run 'clade init' first.", err=True)
        raise SystemExit(1)

    # Header
    click.echo(click.style(config.clade_name, bold=True))
    click.echo(f"Config: {default_config_path()}")
    click.echo()

    # Server status
    if config.server_url:
        server_status = _check_server(config.server_url)
        status_str = click.style("[UP]", fg="green") if server_status else click.style("[DOWN]", fg="red")
        click.echo(f"Server: {config.server_url}  {status_str}")
    else:
        click.echo(f"Server: {click.style('not configured', fg='yellow')}")
    click.echo()

    # Brothers
    click.echo("Brothers:")
    keys = load_keys()

    # Personal
    has_key = config.personal_name in keys
    key_indicator = click.style("[KEY]", fg="green") if has_key else click.style("[NO KEY]", fg="yellow")
    click.echo(f"  {config.personal_name:<12} (personal)   local          {click.style('[OK]', fg='green')}  {key_indicator}")

    # Remote brothers
    for name, bro in config.brothers.items():
        has_key = name in keys
        key_indicator = click.style("[KEY]", fg="green") if has_key else click.style("[NO KEY]", fg="yellow")

        ssh_result = test_ssh(bro.ssh)
        if ssh_result.success:
            ssh_status = click.style("[SSH OK]", fg="green")
        else:
            if "timed out" in ssh_result.message:
                ssh_status = click.style("[SSH TIMEOUT]", fg="red")
            else:
                ssh_status = click.style("[SSH FAIL]", fg="red")

        role = f"({bro.role})"
        click.echo(f"  {name:<12} {role:<12} {bro.ssh:<14} {ssh_status}  {key_indicator}")


def _check_server(url: str) -> bool:
    """Check if the Hearth server is responding."""
    try:
        resp = httpx.get(f"{url}/api/v1/health", timeout=5, verify=False)
        return resp.status_code == 200
    except Exception:
        # Fall back to trying the base URL
        try:
            resp = httpx.get(url, timeout=5, verify=False)
            return resp.status_code in (200, 301, 302)
        except Exception:
            return False
