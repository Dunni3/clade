"""Conductor (Kamaji) deployment — setup on the Hearth server host.

Used by `clade setup-conductor` to deploy the systemd timer, config files,
and identity for the Conductor on EC2.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import click
import yaml

from .clade_config import CladeConfig
from .ember_setup import detect_remote_user
from .identity import generate_conductor_identity, write_identity_remote
from .keys import add_key, keys_path, load_keys
from .ssh_utils import SSHResult, deploy_clade_remote, run_remote, test_ssh

SERVICE_NAME = "conductor-tick"

SERVICE_TEMPLATE = """\
[Unit]
Description=Clade Conductor Tick (Kamaji)
After=network.target

[Service]
Type=oneshot
User={remote_user}
ExecStart={tick_script_path}
EnvironmentFile={env_file_path}
StandardOutput=journal
StandardError=journal
TimeoutStartSec=600
"""

TIMER_TEMPLATE = """\
[Unit]
Description=Run Conductor tick every 30 minutes

[Timer]
OnCalendar=*:0/30
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
"""

# Remote paths
REMOTE_CONFIG_DIR = "~/.config/clade"
REMOTE_TICK_SCRIPT = "~/.config/clade/conductor-tick.sh"
REMOTE_TICK_PROMPT = "~/.config/clade/conductor-tick.md"
REMOTE_ENV_FILE = "~/.config/clade/conductor.env"
REMOTE_WORKERS_CONFIG = "~/.config/clade/conductor-workers.yaml"
REMOTE_MCP_CONFIG = "~/.config/clade/conductor-mcp.json"


def detect_clade_python(ssh_host: str, ssh_key: str | None = None) -> str | None:
    """Detect the Python executable on a remote host that has clade installed.

    Searches common locations (venvs, conda envs, system python) and returns
    the absolute path to the first python that can import clade.mcp.server_conductor.

    Returns:
        Absolute path to python, or None if not found.
    """
    script = """\
#!/bin/bash
for candidate in \
    ~/.local/venv/bin/python3 \
    ~/mambaforge/envs/*/bin/python \
    ~/miniforge3/envs/*/bin/python \
    ~/miniconda3/envs/*/bin/python \
    ~/.conda/envs/*/bin/python \
    $(command -v python3 2>/dev/null); do
    if [ -x "$candidate" ]; then
        if "$candidate" -c "import clade.mcp.server_conductor" 2>/dev/null; then
            # Resolve to absolute path
            realpath "$candidate" 2>/dev/null || readlink -f "$candidate" 2>/dev/null || echo "$candidate"
            exit 0
        fi
    fi
done
echo "NOT_FOUND"
"""
    result = run_remote(ssh_host, script, ssh_key=ssh_key, timeout=15)
    if result.success:
        path = result.stdout.strip().splitlines()[-1]
        if path and path != "NOT_FOUND":
            return path
    return None


def build_workers_config(
    brothers: dict,
    keys: dict[str, str],
) -> str:
    """Build the conductor-workers.yaml content from clade config.

    Only includes brothers that have ember_host set.

    Args:
        brothers: Dict of brother names to BrotherEntry objects.
        keys: Dict of brother names to API keys.

    Returns:
        YAML string for conductor-workers.yaml.
    """
    workers: dict[str, dict] = {}

    for name, bro in brothers.items():
        if not bro.ember_host:
            continue

        api_key = keys.get(name, "")
        port = bro.ember_port or 8100
        workers[name] = {
            "ember_url": f"http://{bro.ember_host}:{port}",
            "ember_api_key": api_key,
            "hearth_api_key": api_key,
        }
        if bro.working_dir:
            workers[name]["working_dir"] = bro.working_dir

    data = {"workers": workers}
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def build_brothers_config(
    brothers: dict,
    keys: dict[str, str],
) -> str:
    """Build brothers-ember.yaml for Ember delegation from personal/worker servers.

    Only includes brothers that have ember_host set.

    Args:
        brothers: Dict of brother names to BrotherEntry objects.
        keys: Dict of brother names to API keys.

    Returns:
        YAML string for brothers-ember.yaml.
    """
    result: dict[str, dict] = {}

    for name, bro in brothers.items():
        if not bro.ember_host:
            continue

        api_key = keys.get(name, "")
        port = bro.ember_port or 8100
        entry: dict[str, str] = {
            "ember_url": f"http://{bro.ember_host}:{port}",
            "ember_api_key": api_key,
            "hearth_api_key": api_key,
        }
        if bro.working_dir:
            entry["working_dir"] = bro.working_dir
        result[name] = entry

    data = {"brothers": result}
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def build_conductor_env(
    kamaji_key: str,
    server_url: str,
    workers_config_path: str = REMOTE_WORKERS_CONFIG,
) -> str:
    """Build the conductor.env file content.

    Args:
        kamaji_key: Kamaji's Hearth API key.
        server_url: Hearth server URL.
        workers_config_path: Path to workers config on remote.

    Returns:
        Env file content string.
    """
    lines = [
        f"HEARTH_URL={server_url}",
        f"HEARTH_API_KEY={kamaji_key}",
        "HEARTH_NAME=kamaji",
        f"CONDUCTOR_WORKERS_CONFIG={workers_config_path}",
    ]
    return "\n".join(lines) + "\n"


def build_conductor_mcp_config(
    kamaji_key: str,
    server_url: str,
    workers_config_path: str = REMOTE_WORKERS_CONFIG,
    python_cmd: str = "python3",
) -> str:
    """Build the conductor-mcp.json for claude --mcp-config.

    Args:
        kamaji_key: Kamaji's Hearth API key.
        server_url: Hearth server URL.
        workers_config_path: Path to workers config on remote.
        python_cmd: Python executable path (should be the one with clade installed).

    Returns:
        JSON string for conductor-mcp.json.
    """
    config = {
        "mcpServers": {
            "clade-conductor": {
                "command": python_cmd,
                "args": ["-m", "clade.mcp.server_conductor"],
                "env": {
                    "HEARTH_URL": server_url,
                    "HEARTH_API_KEY": kamaji_key,
                    "HEARTH_NAME": "kamaji",
                    "CONDUCTOR_WORKERS_CONFIG": workers_config_path,
                },
            }
        }
    }
    return json.dumps(config, indent=2) + "\n"


def _deploy_config_files(
    ssh_host: str,
    workers_yaml: str,
    env_content: str,
    mcp_json: str,
    ssh_key: str | None = None,
) -> SSHResult:
    """Write all config files to the remote host via SSH.

    Writes workers.yaml, conductor.env, and conductor-mcp.json.
    """
    workers_b64 = base64.b64encode(workers_yaml.encode()).decode()
    env_b64 = base64.b64encode(env_content.encode()).decode()
    mcp_b64 = base64.b64encode(mcp_json.encode()).decode()

    script = f"""\
#!/bin/bash
set -e
CONFIG_DIR="$HOME/.config/clade"
mkdir -p "$CONFIG_DIR"

echo "{workers_b64}" | base64 -d > "$CONFIG_DIR/conductor-workers.yaml"
echo "{env_b64}" | base64 -d > "$CONFIG_DIR/conductor.env"
chmod 600 "$CONFIG_DIR/conductor.env"
echo "{mcp_b64}" | base64 -d > "$CONFIG_DIR/conductor-mcp.json"
chmod 600 "$CONFIG_DIR/conductor-mcp.json"
echo "CONFIG_FILES_OK"
"""
    return run_remote(ssh_host, script, ssh_key=ssh_key, timeout=15)


def _deploy_tick_files(ssh_host: str, ssh_key: str | None = None) -> SSHResult:
    """Copy the tick script and prompt to the remote host."""
    # Read local deploy files
    deploy_dir = Path(__file__).resolve().parent.parent.parent.parent / "deploy"
    tick_script = (deploy_dir / "conductor-tick.sh").read_text()
    tick_prompt = (deploy_dir / "conductor-tick.md").read_text()

    script_b64 = base64.b64encode(tick_script.encode()).decode()
    prompt_b64 = base64.b64encode(tick_prompt.encode()).decode()

    script = f"""\
#!/bin/bash
set -e
CONFIG_DIR="$HOME/.config/clade"
mkdir -p "$CONFIG_DIR"

echo "{script_b64}" | base64 -d > "$CONFIG_DIR/conductor-tick.sh"
chmod +x "$CONFIG_DIR/conductor-tick.sh"
echo "{prompt_b64}" | base64 -d > "$CONFIG_DIR/conductor-tick.md"
echo "TICK_FILES_OK"
"""
    return run_remote(ssh_host, script, ssh_key=ssh_key, timeout=15)


def _deploy_systemd(ssh_host: str, remote_user: str, ssh_key: str | None = None) -> SSHResult:
    """Deploy the systemd service and timer, then enable and start the timer."""
    # Expand ~ to /home/<user> for systemd
    home = f"/home/{remote_user}"
    tick_script_path = f"{home}/.config/clade/conductor-tick.sh"
    env_file_path = f"{home}/.config/clade/conductor.env"

    service_content = SERVICE_TEMPLATE.format(
        remote_user=remote_user,
        tick_script_path=tick_script_path,
        env_file_path=env_file_path,
    )
    timer_content = TIMER_TEMPLATE

    service_b64 = base64.b64encode(service_content.encode()).decode()
    timer_b64 = base64.b64encode(timer_content.encode()).decode()

    service_path = f"/etc/systemd/system/{SERVICE_NAME}.service"
    timer_path = f"/etc/systemd/system/{SERVICE_NAME}.timer"

    script = f"""\
#!/bin/bash
set -e
echo "{service_b64}" | base64 -d | sudo tee {service_path} > /dev/null
echo "{timer_b64}" | base64 -d | sudo tee {timer_path} > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable {SERVICE_NAME}.timer
sudo systemctl restart {SERVICE_NAME}.timer
sleep 1
if systemctl is-active --quiet {SERVICE_NAME}.timer; then
    echo "SYSTEMD_OK"
else
    echo "SYSTEMD_FAIL"
    systemctl status {SERVICE_NAME}.timer --no-pager 2>&1 || true
fi
"""
    return run_remote(ssh_host, script, ssh_key=ssh_key, timeout=30)


def deploy_conductor(
    config: CladeConfig,
    config_dir: Path | None = None,
    personality: str | None = None,
    no_identity: bool = False,
    yes: bool = False,
) -> bool:
    """Deploy the Conductor (Kamaji) on the Hearth server host.

    Args:
        config: Loaded CladeConfig.
        config_dir: Override config directory for keys.
        personality: Optional personality for Kamaji.
        no_identity: Skip writing identity.
        yes: Auto-accept prompts.

    Returns:
        True on success, False on failure.
    """
    ssh_host = config.server_ssh
    if not ssh_host:
        click.echo(click.style("No server SSH configured in clade.yaml", fg="red"))
        click.echo("Set server.ssh in clade.yaml or run 'clade init' with --server-ssh")
        return False

    server_url = config.server_url
    if not server_url:
        click.echo(click.style("No server URL configured in clade.yaml", fg="red"))
        return False

    ssh_key = config.server_ssh_key

    # Step 1: Test SSH
    click.echo(f"Testing SSH to {ssh_host}...")
    ssh_result = test_ssh(ssh_host, ssh_key)
    if not ssh_result.success:
        click.echo(click.style(f"  SSH failed: {ssh_result.message}", fg="red"))
        return False
    click.echo(click.style("  SSH OK", fg="green"))

    # Step 2: Detect remote user
    click.echo("Detecting remote user...")
    remote_user = detect_remote_user(ssh_host, ssh_key=ssh_key)
    if not remote_user:
        click.echo(click.style("  Could not detect remote user", fg="red"))
        return False
    click.echo(f"  User: {remote_user}")

    # Step 3: Deploy clade package
    click.echo("Deploying clade package...")
    deploy_result = deploy_clade_remote(ssh_host, ssh_key)
    if deploy_result.success and "DEPLOY_OK" in deploy_result.stdout:
        click.echo(click.style("  Deploy OK", fg="green"))
    else:
        click.echo(click.style(f"  Deploy failed: {deploy_result.message}", fg="red"))
        if deploy_result.stderr:
            click.echo(f"  stderr: {deploy_result.stderr[:200]}")
        if not yes and not click.confirm("Continue anyway?", default=False):
            return False

    # Step 4: Generate Kamaji API key (idempotent)
    kp = keys_path(config_dir)
    keys = load_keys(kp)
    kamaji_key = keys.get("kamaji")
    if kamaji_key:
        click.echo("Kamaji API key already exists in keys.json")
    else:
        kamaji_key = add_key("kamaji", kp)
        click.echo(f"Kamaji API key generated and saved to {kp}")

    # Step 5: Register key with Hearth
    _register_kamaji_key(server_url, config.personal_name, kamaji_key, kp)

    # Step 6: Detect correct Python on remote
    click.echo("Detecting Python with clade installed...")
    python_cmd = detect_clade_python(ssh_host, ssh_key=ssh_key)
    if python_cmd:
        click.echo(click.style(f"  Python: {python_cmd}", fg="green"))
    else:
        python_cmd = "python3"
        click.echo(click.style(f"  Could not detect — falling back to {python_cmd}", fg="yellow"))

    # Step 7: Build config files
    click.echo("Building config files...")
    workers_yaml = build_workers_config(config.brothers, keys)
    env_content = build_conductor_env(kamaji_key, server_url)

    # Expand ~ for the MCP config (it runs via claude, which expands ~)
    mcp_workers_path = f"/home/{remote_user}/.config/clade/conductor-workers.yaml"
    mcp_json = build_conductor_mcp_config(
        kamaji_key, server_url, mcp_workers_path, python_cmd=python_cmd
    )

    # Step 7: Deploy config files
    click.echo("Writing config files to remote...")
    result = _deploy_config_files(ssh_host, workers_yaml, env_content, mcp_json, ssh_key=ssh_key)
    if result.success and "CONFIG_FILES_OK" in result.stdout:
        click.echo(click.style("  Config files written", fg="green"))
    else:
        click.echo(click.style(f"  Failed to write config files: {result.message}", fg="red"))
        return False

    # Step 8: Deploy tick script + prompt
    click.echo("Deploying tick script and prompt...")
    result = _deploy_tick_files(ssh_host, ssh_key=ssh_key)
    if result.success and "TICK_FILES_OK" in result.stdout:
        click.echo(click.style("  Tick files deployed", fg="green"))
    else:
        click.echo(click.style(f"  Failed to deploy tick files: {result.message}", fg="red"))
        return False

    # Step 9: Deploy systemd service + timer
    click.echo("Deploying systemd service and timer...")
    result = _deploy_systemd(ssh_host, remote_user, ssh_key=ssh_key)
    if result.success and "SYSTEMD_OK" in result.stdout:
        click.echo(click.style("  Timer deployed and active", fg="green"))
    elif "SYSTEMD_FAIL" in (result.stdout or ""):
        click.echo(click.style("  Timer deployed but not active", fg="red"))
        return False
    else:
        click.echo(click.style("  Systemd deployment failed (sudo may be required)", fg="red"))
        if result.stderr:
            click.echo(f"  Error: {result.stderr[:200]}")
        return False

    # Step 10: Write Kamaji's identity
    if not no_identity:
        click.echo("Writing Kamaji's identity...")

        # Build workers and brothers info for identity
        workers_info = {}
        brothers_info = {}
        for bro_name, bro in config.brothers.items():
            brothers_info[bro_name] = {
                "role": bro.role,
                "description": bro.description,
            }
            if bro.ember_host:
                workers_info[bro_name] = {
                    "description": bro.description,
                }

        identity = generate_conductor_identity(
            name="kamaji",
            clade_name=config.clade_name,
            personality=personality or "Gruff and no-nonsense, but quietly kind underneath.",
            workers=workers_info,
            brothers=brothers_info,
        )
        result = write_identity_remote(ssh_host, identity, ssh_key=ssh_key)
        if result.success and "IDENTITY_OK" in result.stdout:
            click.echo(click.style("  Identity written", fg="green"))
        else:
            click.echo(click.style(f"  Identity write failed: {result.message}", fg="yellow"))

    return True


def _register_kamaji_key(
    server_url: str,
    personal_name: str,
    kamaji_key: str,
    kp: Path,
) -> None:
    """Register Kamaji's API key with the Hearth."""
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
        ok = client.register_key_sync("kamaji", kamaji_key)
        if ok:
            click.echo("Registered 'kamaji' key with the Hearth")
        else:
            click.echo(
                click.style("  Warning: failed to register key with Hearth", fg="yellow")
            )
    except Exception as e:
        click.echo(
            click.style(f"  Warning: could not reach Hearth to register key: {e}", fg="yellow")
        )
