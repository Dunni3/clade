"""clade add-brother — add and configure a new brother."""

from __future__ import annotations

import click

from .clade_config import (
    BrotherEntry,
    default_brothers_config_path,
    default_config_path,
    load_clade_config,
    save_clade_config,
)
from .conductor_setup import build_brothers_config
from .ember_setup import (
    detect_remote_user,
    detect_systemctl_path,
    generate_sudoers_command,
    install_sudoers_remote,
    setup_ember,
    verify_sudoers_remote,
)
from .identity import generate_worker_identity, write_identity_remote
from .keys import add_key, keys_path, load_keys
from .mcp_utils import register_mcp_remote, update_mcp_env, update_mcp_env_remote
from .naming import format_suggestion, suggest_name
from .ssh_utils import check_remote_prereqs, deploy_clade_remote, run_remote, test_ssh


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
@click.option("--ember", "setup_ember_flag", is_flag=True, help="Set up an Ember server on the remote")
@click.option("--ember-port", default=None, type=int, help="Ember server port (default: 8100)")
@click.option("--sudoers", "setup_sudoers", is_flag=True, help="Set up passwordless sudo for Ember restarts")
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
    setup_ember_flag: bool,
    ember_port: int | None,
    setup_sudoers: bool,
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

    # Register API key with the Hearth
    if config.server_url:
        _register_key_with_hearth(config.server_url, config.personal_name, name, api_key, kp)

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

    # Ember setup
    ember_host = None
    actual_ember_port = None
    if setup_ember_flag and ssh_result.success:
        # Load caller's key for Hearth registration
        all_keys = load_keys(kp)
        caller_key = all_keys.get(config.personal_name) or api_key
        ember_host, actual_ember_port = setup_ember(
            ssh_host=ssh_host,
            name=name,
            api_key=api_key,
            port=ember_port or 8100,
            working_dir=working_dir,
            server_url=config.server_url,
            yes=yes,
            hearth_api_key=caller_key,
        )

    # Sudoers setup
    sudoers_ok = False
    if setup_sudoers and setup_ember_flag and ember_host and ssh_result.success:
        sudoers_ok = _setup_sudoers(ssh_host)

    # Update config
    config.brothers[name] = BrotherEntry(
        ssh=ssh_host,
        working_dir=working_dir,
        role=role,
        description=desc,
        personality=personality,
        ember_port=actual_ember_port if ember_host else None,
        ember_host=ember_host,
        sudoers_configured=sudoers_ok,
    )
    config_path = default_config_path(config_dir)
    save_clade_config(config, config_path)
    click.echo(f"Brother '{name}' added to {config_path}")

    # Regenerate brothers-ember.yaml if any brother has Ember
    all_keys = load_keys(keys_path(config_dir))
    has_ember_brothers = any(b.ember_host for b in config.brothers.values())
    if has_ember_brothers:
        brothers_yaml = build_brothers_config(config.brothers, all_keys)
        brothers_path = default_brothers_config_path(config_dir)
        brothers_path.parent.mkdir(parents=True, exist_ok=True)
        brothers_path.write_text(brothers_yaml)
        click.echo(f"Brothers config written to {brothers_path}")

        # Update local MCP env to point to brothers config
        updated = update_mcp_env("clade-personal", {"BROTHERS_CONFIG": str(brothers_path)})
        if updated:
            click.echo("  Updated local clade-personal MCP env")

        # Deploy brothers config to each Ember brother and update their remote MCP env
        for bro_name, bro in config.brothers.items():
            if not bro.ember_host:
                continue
            _deploy_brothers_config_remote(
                ssh_host=bro.ssh,
                brothers_yaml=brothers_yaml,
            )

    # Summary
    click.echo()
    click.echo(click.style("Summary:", bold=True))
    click.echo(f"  Name: {name}")
    click.echo(f"  SSH:  {ssh_host}")
    if working_dir:
        click.echo(f"  Dir:  {working_dir}")
    click.echo(f"  Role: {role}")
    if ember_host:
        click.echo(f"  Ember: {ember_host}:{actual_ember_port}")

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
    result = deploy_clade_remote(ssh_host)
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


def _register_key_with_hearth(
    server_url: str,
    personal_name: str,
    brother_name: str,
    brother_key: str,
    kp,
) -> None:
    """Register the brother's API key with the Hearth using the personal brother's key."""
    from ..communication.mailbox_client import MailboxClient

    keys = load_keys(kp)
    personal_key = keys.get(personal_name)
    if not personal_key:
        click.echo(
            click.style(
                f"  Warning: no API key found for '{personal_name}' — cannot register with Hearth",
                fg="yellow",
            )
        )
        return

    verify_ssl = server_url.startswith("https")
    client = MailboxClient(server_url, personal_key, verify_ssl=verify_ssl)
    try:
        ok = client.register_key_sync(brother_name, brother_key)
        if ok:
            click.echo(f"Registered '{brother_name}' key with the Hearth")
        else:
            click.echo(
                click.style(f"  Warning: failed to register key with Hearth", fg="yellow")
            )
    except Exception as e:
        click.echo(
            click.style(f"  Warning: could not reach Hearth to register key: {e}", fg="yellow")
        )


def _deploy_brothers_config_remote(
    ssh_host: str,
    brothers_yaml: str,
) -> None:
    """Deploy brothers-ember.yaml to a remote brother and update their MCP env."""
    import base64

    encoded = base64.b64encode(brothers_yaml.encode()).decode()
    script = f"""\
#!/bin/bash
set -e
CONFIG_DIR="$HOME/.config/clade"
mkdir -p "$CONFIG_DIR"
echo "{encoded}" | base64 -d > "$CONFIG_DIR/brothers-ember.yaml"
echo "BROTHERS_CONFIG_OK"
"""
    result = run_remote(ssh_host, script, timeout=15)
    if result.success and "BROTHERS_CONFIG_OK" in result.stdout:
        click.echo(click.style(f"  Deployed brothers config to {ssh_host}", fg="green"))
        # Update remote MCP env
        env_result = update_mcp_env_remote(
            ssh_host,
            "clade-worker",
            {"BROTHERS_CONFIG": "~/.config/clade/brothers-ember.yaml"},
        )
        if env_result.success and "ENV_UPDATED" in env_result.stdout:
            click.echo(click.style(f"  Updated remote clade-worker MCP env on {ssh_host}", fg="green"))
    else:
        click.echo(click.style(f"  Warning: failed to deploy brothers config to {ssh_host}", fg="yellow"))


def _setup_sudoers(ssh_host: str) -> bool:
    """Set up passwordless sudo for Ember service restarts.

    Returns True if sudoers was successfully configured and verified.
    """
    click.echo()
    click.echo(click.style("Setting up passwordless sudo for Ember restarts...", bold=True))

    remote_user = detect_remote_user(ssh_host)
    if not remote_user:
        click.echo(click.style("  Could not detect remote user", fg="red"))
        return False

    systemctl_path = detect_systemctl_path(ssh_host)
    if not systemctl_path:
        click.echo(click.style("  Could not detect systemctl path on remote", fg="red"))
        return False

    click.echo(f"  User: {remote_user}")
    click.echo(f"  systemctl: {systemctl_path}")

    cmd = generate_sudoers_command(ssh_host, remote_user, systemctl_path)
    click.echo()
    click.echo("  The following command will install a scoped sudoers rule:")
    click.echo()
    click.echo(f"    {cmd}")
    click.echo()

    if not click.confirm("  Install this sudoers rule now?", default=True):
        click.echo("  Skipped. You can run the command above manually.")
        return False

    result = install_sudoers_remote(ssh_host, remote_user, systemctl_path)
    if not result.success or "SUDOERS_OK" not in result.stdout:
        click.echo(click.style("  Failed to install sudoers rule", fg="red"))
        if result.stderr:
            click.echo(f"  Error: {result.stderr[:200]}")
        click.echo("  You can run the command above manually instead.")
        return False

    click.echo(click.style("  Sudoers rule installed", fg="green"))

    click.echo("  Verifying passwordless sudo...")
    if verify_sudoers_remote(ssh_host, systemctl_path):
        click.echo(click.style("  Verification passed!", fg="green"))
        return True
    else:
        click.echo(click.style("  Verification failed — sudo may still require a password", fg="yellow"))
        return False
