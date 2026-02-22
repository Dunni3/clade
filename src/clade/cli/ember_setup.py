"""Ember server setup — detection, deployment, and health checking.

Used by both `clade setup-ember` and `clade add-brother --ember`.
"""

from __future__ import annotations

import base64

import click
import httpx

from .ssh_utils import SSHResult, run_remote

SERVICE_NAME = "clade-ember"

SERVICE_TEMPLATE = """\
[Unit]
Description=Clade Ember Server ({brother_name})
After=network.target

[Service]
Type=simple
User={remote_user}
WorkingDirectory={clade_dir}
ExecStart={clade_ember_path}
Restart=always
RestartSec=5
EnvironmentFile={env_file_path}

[Install]
WantedBy=multi-user.target
"""

EMBER_ENV_TEMPLATE = """\
EMBER_PORT={port}
EMBER_BROTHER_NAME={brother_name}
EMBER_WORKING_DIR={working_dir}
HEARTH_URL={hearth_url}
HEARTH_API_KEY={api_key}
HEARTH_NAME={brother_name}
"""


def detect_remote_user(ssh_host: str, ssh_key: str | None = None) -> str | None:
    """Detect the remote username via whoami."""
    result = run_remote(ssh_host, "whoami", ssh_key=ssh_key, timeout=10)
    if result.success:
        return result.stdout.strip()
    return None


def detect_clade_ember_path(ssh_host: str, ssh_key: str | None = None) -> str | None:
    """Detect the path to the clade-ember binary on the remote.

    Tries `which` first, then searches common conda/mamba/venv locations
    since non-interactive SSH sessions don't activate environments.
    """
    result = run_remote(ssh_host, "which clade-ember 2>/dev/null", ssh_key=ssh_key, timeout=10)
    if result.success and result.stdout.strip():
        return result.stdout.strip()

    # Search common env locations
    search_script = r"""
for d in \
    ~/mambaforge/envs/*/bin \
    ~/miniforge3/envs/*/bin \
    ~/miniconda3/envs/*/bin \
    ~/anaconda3/envs/*/bin \
    ~/.conda/envs/*/bin \
    ~/.local/venv/bin \
    ~/.local/bin; do
    if [ -x "$d/clade-ember" ]; then
        echo "$d/clade-ember"
        exit 0
    fi
done
exit 1
"""
    result = run_remote(ssh_host, search_script, ssh_key=ssh_key, timeout=10)
    if result.success and result.stdout.strip():
        return result.stdout.strip()
    return None


def detect_clade_dir(ssh_host: str, ssh_key: str | None = None) -> str | None:
    """Detect the clade package directory on the remote (for WorkingDirectory).

    Tries the system python first, then searches conda/mamba/venv pythons
    since non-interactive SSH won't have the environment activated.
    """
    import_cmd = 'import clade, os; print(os.path.dirname(os.path.dirname(clade.__file__)))'

    # Try system python first
    result = run_remote(ssh_host, f'python3 -c "{import_cmd}" 2>/dev/null', ssh_key=ssh_key, timeout=10)
    if result.success and result.stdout.strip().startswith("/"):
        return result.stdout.strip()

    # Search conda/mamba/venv pythons
    search_script = f"""
for py in \\
    ~/mambaforge/envs/*/bin/python \\
    ~/miniforge3/envs/*/bin/python \\
    ~/miniconda3/envs/*/bin/python \\
    ~/anaconda3/envs/*/bin/python \\
    ~/.conda/envs/*/bin/python \\
    ~/.local/venv/bin/python; do
    if [ -x "$py" ]; then
        result=$("$py" -c "{import_cmd}" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$result" ]; then
            echo "$result"
            exit 0
        fi
    fi
done
exit 1
"""
    result = run_remote(ssh_host, search_script, ssh_key=ssh_key, timeout=15)
    if result.success and result.stdout.strip().startswith("/"):
        return result.stdout.strip()
    return None


def detect_tailscale_ip(ssh_host: str, ssh_key: str | None = None) -> str | None:
    """Detect the Tailscale IPv4 address on the remote, if available."""
    result = run_remote(ssh_host, "tailscale ip -4 2>/dev/null", ssh_key=ssh_key, timeout=10)
    if result.success and result.stdout.strip():
        ip = result.stdout.strip()
        if ip.startswith("100."):
            return ip
    return None


def deploy_ember_env(
    ssh_host: str,
    remote_user: str,
    brother_name: str,
    port: int,
    working_dir: str,
    hearth_url: str,
    api_key: str,
    ssh_key: str | None = None,
) -> SSHResult:
    """Write (or update) the Ember env file on the remote host.

    The file lives at ``~/.config/clade/ember.env`` (user-owned, no sudo).

    Returns:
        SSHResult from the operation.
    """
    env_content = EMBER_ENV_TEMPLATE.format(
        port=port,
        brother_name=brother_name,
        working_dir=working_dir,
        hearth_url=hearth_url,
        api_key=api_key,
    )
    encoded = base64.b64encode(env_content.encode()).decode()

    script = f"""\
#!/bin/bash
set -e
CONFIG_DIR="$HOME/.config/clade"
mkdir -p "$CONFIG_DIR"
echo "{encoded}" | base64 -d > "$CONFIG_DIR/ember.env"
chmod 600 "$CONFIG_DIR/ember.env"
echo "EMBER_ENV_OK"
"""
    return run_remote(ssh_host, script, ssh_key=ssh_key, timeout=15)


def deploy_systemd_service(
    ssh_host: str,
    brother_name: str,
    remote_user: str,
    clade_ember_path: str,
    clade_dir: str,
    port: int,
    working_dir: str,
    hearth_url: str,
    api_key: str,
    ssh_key: str | None = None,
) -> SSHResult:
    """Deploy the systemd service file, env file, and start the Ember server.

    Returns:
        SSHResult from the deployment.
    """
    # Write the env file first (no sudo needed)
    env_result = deploy_ember_env(
        ssh_host=ssh_host,
        remote_user=remote_user,
        brother_name=brother_name,
        port=port,
        working_dir=working_dir,
        hearth_url=hearth_url,
        api_key=api_key,
        ssh_key=ssh_key,
    )
    if not env_result.success or "EMBER_ENV_OK" not in env_result.stdout:
        return env_result

    # Build the service file (references the env file via EnvironmentFile=)
    home = f"/home/{remote_user}"
    env_file_path = f"{home}/.config/clade/ember.env"

    service_content = SERVICE_TEMPLATE.format(
        brother_name=brother_name,
        remote_user=remote_user,
        clade_ember_path=clade_ember_path,
        clade_dir=clade_dir,
        env_file_path=env_file_path,
    )

    encoded = base64.b64encode(service_content.encode()).decode()
    service_path = f"/etc/systemd/system/{SERVICE_NAME}.service"

    script = f"""\
#!/bin/bash
set -e
echo "{encoded}" | base64 -d | sudo tee {service_path} > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable {SERVICE_NAME}
sudo systemctl restart {SERVICE_NAME}
sleep 2
if systemctl is-active --quiet {SERVICE_NAME}; then
    echo "EMBER_DEPLOY_OK"
else
    echo "EMBER_DEPLOY_FAIL"
    sudo journalctl -u {SERVICE_NAME} --no-pager -n 10
fi
"""
    return run_remote(ssh_host, script, ssh_key=ssh_key, timeout=30)


def check_ember_health_remote(host: str, port: int) -> bool:
    """Check if the Ember server is responding via HTTP."""
    try:
        resp = httpx.get(f"http://{host}:{port}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def generate_manual_instructions(
    brother_name: str,
    remote_user: str,
    clade_ember_path: str,
    clade_dir: str,
    port: int,
    working_dir: str,
    hearth_url: str,
    api_key: str,
) -> str:
    """Generate manual setup instructions when sudo is not available."""
    home = f"/home/{remote_user}"
    env_file_path = f"{home}/.config/clade/ember.env"

    env_content = EMBER_ENV_TEMPLATE.format(
        port=port,
        brother_name=brother_name,
        working_dir=working_dir,
        hearth_url=hearth_url,
        api_key=api_key,
    )
    service_content = SERVICE_TEMPLATE.format(
        brother_name=brother_name,
        remote_user=remote_user,
        clade_ember_path=clade_ember_path,
        clade_dir=clade_dir,
        env_file_path=env_file_path,
    )
    return f"""\
Could not deploy automatically (sudo required). Manual steps:

1. Create the env file at {env_file_path}:

{env_content}
   chmod 600 {env_file_path}

2. Create the service file at /etc/systemd/system/{SERVICE_NAME}.service:

{service_content}
3. Run:
   sudo systemctl daemon-reload
   sudo systemctl enable {SERVICE_NAME}
   sudo systemctl restart {SERVICE_NAME}

4. Verify:
   systemctl status {SERVICE_NAME}
   curl http://localhost:{port}/health
"""


def setup_ember(
    ssh_host: str,
    name: str,
    api_key: str,
    port: int,
    working_dir: str | None,
    server_url: str | None,
    ssh_key: str | None = None,
    yes: bool = False,
    hearth_api_key: str | None = None,
    verify_ssl: bool = True,
) -> tuple[str | None, int]:
    """Set up an Ember server on a remote brother.

    Args:
        ssh_host: SSH host string.
        name: Brother name.
        api_key: The brother's Hearth API key.
        port: Ember port.
        working_dir: Working directory for tasks (from config or flag).
        server_url: Hearth server URL.
        ssh_key: Optional path to SSH private key.
        yes: Auto-accept prompts.

    Returns:
        (ember_host, port) on success, (None, port) on failure.
    """
    click.echo(f"\nSetting up Ember server on {ssh_host}...")

    # Detect remote user
    click.echo("  Detecting remote user...")
    remote_user = detect_remote_user(ssh_host, ssh_key=ssh_key)
    if not remote_user:
        click.echo(click.style("  Could not detect remote user", fg="red"))
        return None, port
    click.echo(f"  User: {remote_user}")

    # Detect clade-ember path
    click.echo("  Detecting clade-ember binary...")
    ember_path = detect_clade_ember_path(ssh_host, ssh_key=ssh_key)
    if not ember_path:
        click.echo(click.style("  clade-ember not found on remote", fg="red"))
        click.echo("  Make sure the clade package is installed (pip install -e .)")
        return None, port
    click.echo(f"  Binary: {ember_path}")

    # Detect clade directory (for WorkingDirectory)
    click.echo("  Detecting clade package directory...")
    clade_dir = detect_clade_dir(ssh_host, ssh_key=ssh_key)
    if not clade_dir:
        clade_dir = f"/home/{remote_user}"
        click.echo(click.style(f"  Could not detect, using {clade_dir}", fg="yellow"))
    else:
        click.echo(f"  Directory: {clade_dir}")

    # Detect Tailscale IP
    click.echo("  Detecting Tailscale IP...")
    tailscale_ip = detect_tailscale_ip(ssh_host, ssh_key=ssh_key)
    if tailscale_ip:
        click.echo(f"  Tailscale: {tailscale_ip}")
        ember_host = tailscale_ip
    else:
        click.echo(click.style("  Tailscale not available", fg="yellow"))
        ember_host = ssh_host.split("@")[-1] if "@" in ssh_host else ssh_host

    # Resolve working dir
    effective_working_dir = working_dir or f"/home/{remote_user}"
    hearth_url = server_url or ""

    # Deploy service
    click.echo("  Deploying systemd service...")
    result = deploy_systemd_service(
        ssh_host=ssh_host,
        brother_name=name,
        remote_user=remote_user,
        clade_ember_path=ember_path,
        clade_dir=clade_dir,
        port=port,
        working_dir=effective_working_dir,
        hearth_url=hearth_url,
        api_key=api_key,
        ssh_key=ssh_key,
    )

    if result.success and "EMBER_DEPLOY_OK" in result.stdout:
        click.echo(click.style("  Service deployed and running", fg="green"))
    elif "EMBER_DEPLOY_FAIL" in result.stdout:
        click.echo(click.style("  Service deployed but failed to start", fg="red"))
        if result.stdout:
            # Show journal lines after the FAIL marker
            lines = result.stdout.split("EMBER_DEPLOY_FAIL")[-1].strip()
            if lines:
                click.echo(f"  Journal:\n{lines}")
        return None, port
    else:
        click.echo(click.style("  Deployment failed (sudo may be required)", fg="red"))
        if result.stderr:
            click.echo(f"  Error: {result.stderr[:200]}")
        instructions = generate_manual_instructions(
            brother_name=name,
            remote_user=remote_user,
            clade_ember_path=ember_path,
            clade_dir=clade_dir,
            port=port,
            working_dir=effective_working_dir,
            hearth_url=hearth_url,
            api_key=api_key,
        )
        click.echo(instructions)
        return None, port

    # Health check
    click.echo(f"  Checking health at {ember_host}:{port}...")
    if check_ember_health_remote(ember_host, port):
        click.echo(click.style("  Ember is healthy!", fg="green"))
    else:
        click.echo(click.style("  Health check failed (may need a moment to start)", fg="yellow"))

    # Register ember with the Hearth (best-effort)
    if server_url and hearth_api_key:
        try:
            from ..communication.mailbox_client import MailboxClient

            client = MailboxClient(server_url, hearth_api_key, verify_ssl=verify_ssl)
            ok = client.register_ember_sync(name, f"http://{ember_host}:{port}")
            if ok:
                click.echo(f"  Registered ember with Hearth")
            else:
                click.echo(click.style("  Warning: failed to register ember with Hearth", fg="yellow"))
        except Exception as e:
            click.echo(click.style(f"  Warning: could not register ember with Hearth: {e}", fg="yellow"))

    return ember_host, port
