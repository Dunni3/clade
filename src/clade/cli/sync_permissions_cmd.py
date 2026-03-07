"""clade sync-permissions — upload clade.yaml permissions to the Hearth."""

from __future__ import annotations

import click

from .clade_config import (
    build_permission_flags,
    default_config_path,
    load_clade_config,
)
from .keys import keys_path, load_keys


@click.command()
@click.pass_context
def sync_permissions(ctx: click.Context) -> None:
    """Upload permission settings from clade.yaml to the Hearth.

    For each brother with an Ember registered, reads the local permissions
    from clade.yaml and writes the resolved permission_flags to the Hearth.
    The Hearth becomes the authoritative source; Embers will fetch from it
    on their next task execution.

    Requires HEARTH_URL and HEARTH_API_KEY to be set, or a server URL
    configured in clade.yaml.
    """
    from ..communication.mailbox_client import MailboxClient

    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    config = load_clade_config(default_config_path(config_dir))
    if config is None:
        click.echo("No clade.yaml found. Run 'clade init' first.", err=True)
        raise SystemExit(1)

    if not config.server_url:
        click.echo("No Hearth server URL configured in clade.yaml.", err=True)
        click.echo("Set 'server.url' in clade.yaml or configure HEARTH_URL.", err=True)
        raise SystemExit(1)

    kp = keys_path(config_dir)
    keys = load_keys(kp)
    personal_key = keys.get(config.personal_name)
    if not personal_key:
        click.echo(
            f"No API key found for '{config.personal_name}' in {kp}.", err=True
        )
        raise SystemExit(1)

    client = MailboxClient(config.server_url, personal_key, verify_ssl=config.verify_ssl)

    brothers_with_ember = [
        (name, bro) for name, bro in config.brothers.items() if bro.ember_host
    ]
    if not brothers_with_ember:
        click.echo("No brothers with Ember configured — nothing to sync.")
        return

    click.echo(f"Syncing permissions for {len(brothers_with_ember)} brother(s) to Hearth...")
    success = 0
    for name, bro in brothers_with_ember:
        flags = build_permission_flags(bro.permissions)
        try:
            ok = client.set_ember_permissions_sync(name, flags)
            if ok:
                desc = flags or "(CC defaults)"
                click.echo(click.style(f"  {name}: {desc}", fg="green"))
                success += 1
            else:
                click.echo(click.style(f"  {name}: failed to write (Hearth returned error)", fg="red"))
        except Exception as e:
            click.echo(click.style(f"  {name}: error — {e}", fg="red"))

    click.echo(f"\nDone: {success}/{len(brothers_with_ember)} brothers synced.")
