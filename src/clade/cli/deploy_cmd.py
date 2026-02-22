"""clade deploy — deploy Clade infrastructure components.

Subcommands: hearth, frontend, conductor, ember, all.
Each reads SSH config from clade.yaml, uses tar-pipe-SSH for file transfer,
and is non-interactive by default.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
import httpx

from .clade_config import default_config_path, load_clade_config
from .conductor_setup import deploy_conductor
from .deploy_utils import (
    deploy_clade_package,
    load_config_or_exit,
    require_server_ssh,
    scp_build_directory,
    scp_directory,
)
from .ember_setup import SERVICE_NAME as EMBER_SERVICE_NAME
from .ember_setup import check_ember_health_remote, deploy_ember_env, detect_remote_user
from .keys import keys_path, load_keys
from .ssh_utils import run_remote, test_ssh


@click.group()
@click.pass_context
def deploy(ctx: click.Context) -> None:
    """Deploy Clade infrastructure components."""
    pass


@deploy.command()
@click.pass_context
def hearth(ctx: click.Context) -> None:
    """Deploy the Hearth server (code + restart)."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    config = load_config_or_exit(config_dir)
    ssh_host, ssh_key = require_server_ssh(config)

    # Step 1: Test SSH
    click.echo(f"Testing SSH to {ssh_host}...")
    result = test_ssh(ssh_host, ssh_key)
    if not result.success:
        click.echo(click.style(f"  SSH failed: {result.message}", fg="red"))
        raise SystemExit(1)
    click.echo(click.style("  SSH OK", fg="green"))

    # Step 2: Copy hearth code
    hearth_dir = Path(__file__).resolve().parent.parent.parent.parent / "hearth"
    if not hearth_dir.is_dir():
        click.echo(click.style(f"  hearth/ directory not found at {hearth_dir}", fg="red"))
        raise SystemExit(1)

    click.echo("Deploying hearth code...")
    result = scp_directory(hearth_dir, ssh_host, "/opt/hearth/hearth", ssh_key=ssh_key)
    if not result.success:
        click.echo(click.style(f"  Failed: {result.message}", fg="red"))
        if result.stderr:
            click.echo(f"  {result.stderr[:200]}")
        raise SystemExit(1)
    click.echo(click.style("  Code deployed", fg="green"))

    # Step 3: Install dependencies
    click.echo("Installing dependencies...")
    result = run_remote(
        ssh_host,
        "sudo /opt/hearth/venv/bin/pip install -r /opt/hearth/hearth/requirements.txt 2>&1 | tail -3",
        ssh_key=ssh_key,
        timeout=60,
    )
    if not result.success:
        click.echo(click.style(f"  pip install failed: {result.message}", fg="red"))
        if result.stderr:
            click.echo(f"  {result.stderr[:200]}")
        raise SystemExit(1)
    click.echo(click.style("  Dependencies installed", fg="green"))

    # Step 4: Restart service
    click.echo("Restarting hearth service...")
    result = run_remote(
        ssh_host,
        "sudo systemctl restart hearth && sleep 1 && systemctl is-active --quiet hearth && echo RESTART_OK",
        ssh_key=ssh_key,
        timeout=15,
    )
    if not result.success or "RESTART_OK" not in result.stdout:
        click.echo(click.style("  Restart failed", fg="red"))
        if result.stderr:
            click.echo(f"  {result.stderr[:200]}")
        raise SystemExit(1)
    click.echo(click.style("  Service restarted", fg="green"))

    # Step 5: Health check
    server_url = config.server_url
    if server_url:
        click.echo("Running health check...")
        try:
            resp = httpx.get(
                f"{server_url}/api/v1/health",
                timeout=10,
                verify=not server_url.startswith("https"),
            )
            if resp.status_code == 200:
                click.echo(click.style("  Health check passed", fg="green"))
            else:
                click.echo(click.style(f"  Health check returned {resp.status_code}", fg="yellow"))
        except Exception as e:
            click.echo(click.style(f"  Health check failed: {e}", fg="yellow"))

    click.echo(click.style("\nHearth deployed successfully!", fg="green", bold=True))


@deploy.command()
@click.option("--skip-build", is_flag=True, help="Skip npm run build")
@click.pass_context
def frontend(ctx: click.Context, skip_build: bool) -> None:
    """Build and deploy the frontend."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    config = load_config_or_exit(config_dir)
    ssh_host, ssh_key = require_server_ssh(config)

    frontend_dir = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
    if not frontend_dir.is_dir():
        click.echo(click.style(f"  frontend/ directory not found at {frontend_dir}", fg="red"))
        raise SystemExit(1)

    # Step 1: Build
    if not skip_build:
        click.echo("Building frontend...")
        try:
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=str(frontend_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                click.echo(click.style("  Build failed", fg="red"))
                if result.stderr:
                    click.echo(f"  {result.stderr[:300]}")
                raise SystemExit(1)
            click.echo(click.style("  Build complete", fg="green"))
        except FileNotFoundError:
            click.echo(click.style("  npm not found", fg="red"))
            raise SystemExit(1)
        except subprocess.TimeoutExpired:
            click.echo(click.style("  Build timed out", fg="red"))
            raise SystemExit(1)
    else:
        click.echo("Skipping build (--skip-build)")

    dist_dir = frontend_dir / "dist"
    if not dist_dir.is_dir():
        click.echo(click.style(f"  dist/ not found at {dist_dir} — run build first", fg="red"))
        raise SystemExit(1)

    # Step 2: Test SSH
    click.echo(f"Testing SSH to {ssh_host}...")
    result = test_ssh(ssh_host, ssh_key)
    if not result.success:
        click.echo(click.style(f"  SSH failed: {result.message}", fg="red"))
        raise SystemExit(1)
    click.echo(click.style("  SSH OK", fg="green"))

    # Step 3: Deploy via staging
    click.echo("Deploying frontend...")
    result = scp_build_directory(dist_dir, ssh_host, "/var/www/hearth", ssh_key=ssh_key)
    if not result.success:
        click.echo(click.style(f"  Deploy failed: {result.message}", fg="red"))
        if result.stderr:
            click.echo(f"  {result.stderr[:200]}")
        raise SystemExit(1)
    click.echo(click.style("  Frontend deployed", fg="green"))

    # Step 4: Verify
    server_url = config.server_url
    if server_url:
        click.echo("Verifying site loads...")
        try:
            resp = httpx.get(
                server_url,
                timeout=10,
                verify=not server_url.startswith("https"),
                follow_redirects=True,
            )
            if resp.status_code == 200:
                click.echo(click.style("  Site loads OK", fg="green"))
            else:
                click.echo(click.style(f"  Site returned {resp.status_code}", fg="yellow"))
        except Exception as e:
            click.echo(click.style(f"  Could not verify: {e}", fg="yellow"))

    click.echo(click.style("\nFrontend deployed successfully!", fg="green", bold=True))


@deploy.command()
@click.option("--personality", default=None, help="Personality description for Kamaji")
@click.option("--no-identity", is_flag=True, help="Skip writing identity")
@click.pass_context
def conductor(ctx: click.Context, personality: str | None, no_identity: bool) -> None:
    """Deploy the Conductor (Kamaji) on the Hearth server."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    config = load_config_or_exit(config_dir)

    click.echo(click.style("Deploying Conductor (Kamaji)...", bold=True))

    success = deploy_conductor(
        config=config,
        config_dir=config_dir,
        personality=personality,
        no_identity=no_identity,
        yes=True,  # Non-interactive
    )

    if success:
        click.echo(click.style("\nConductor deployed successfully!", fg="green", bold=True))
    else:
        click.echo(click.style("\nConductor deployment failed.", fg="red"))
        raise SystemExit(1)


@deploy.command()
@click.argument("name")
@click.pass_context
def ember(ctx: click.Context, name: str) -> None:
    """Deploy updated clade code to an Ember brother and restart.

    NAME is the brother name (e.g., 'oppy').

    This updates the clade package and restarts the Ember service.
    For initial Ember setup, use 'clade setup-ember' instead.
    """
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    config = load_config_or_exit(config_dir)

    # Look up brother
    if name not in config.brothers:
        click.echo(click.style(f"Brother '{name}' not found in clade.yaml", fg="red"))
        available = ", ".join(config.brothers.keys()) if config.brothers else "(none)"
        click.echo(f"Available brothers: {available}")
        raise SystemExit(1)

    brother = config.brothers[name]
    if not brother.ember_host:
        click.echo(click.style(f"Brother '{name}' has no ember_host configured", fg="red"))
        click.echo("Run 'clade setup-ember' first to set up Ember on this brother")
        raise SystemExit(1)

    ssh_host = brother.ssh
    ssh_key = None  # Brothers use SSH config, not explicit keys

    # Step 1: Test SSH
    click.echo(f"Testing SSH to {ssh_host}...")
    result = test_ssh(ssh_host)
    if not result.success:
        click.echo(click.style(f"  SSH failed: {result.message}", fg="red"))
        raise SystemExit(1)
    click.echo(click.style("  SSH OK", fg="green"))

    # Step 2: Deploy clade package
    click.echo("Deploying clade package...")
    result = deploy_clade_package(ssh_host, ssh_key=ssh_key)
    if not result.success or "DEPLOY_OK" not in result.stdout:
        click.echo(click.style(f"  Deploy failed: {result.message}", fg="red"))
        if result.stderr:
            click.echo(f"  {result.stderr[:200]}")
        raise SystemExit(1)
    click.echo(click.style("  Package deployed", fg="green"))

    # Step 3: Sync ember.env with current API key from keys.json
    click.echo("Syncing ember.env with current API key...")
    all_keys = load_keys(keys_path(config_dir))
    brother_key = all_keys.get(name)
    if not brother_key:
        click.echo(click.style(f"  No API key found for '{name}' in keys.json", fg="red"))
        raise SystemExit(1)

    remote_user = detect_remote_user(ssh_host, ssh_key=ssh_key)
    if not remote_user:
        click.echo(click.style("  Could not detect remote user", fg="red"))
        raise SystemExit(1)

    ember_port = brother.ember_port or 8100
    env_result = deploy_ember_env(
        ssh_host=ssh_host,
        remote_user=remote_user,
        brother_name=name,
        port=ember_port,
        working_dir=brother.working_dir or f"/home/{remote_user}",
        hearth_url=config.server_url or "",
        api_key=brother_key,
        ssh_key=ssh_key,
    )
    if env_result.success and "EMBER_ENV_OK" in env_result.stdout:
        click.echo(click.style("  ember.env synced", fg="green"))
    else:
        click.echo(click.style("  Warning: could not sync ember.env", fg="yellow"))

    # Step 4: Restart Ember service
    click.echo("Restarting Ember service...")
    restart_script = (
        f"sudo systemctl restart {EMBER_SERVICE_NAME} && sleep 2 && "
        f"systemctl is-active --quiet {EMBER_SERVICE_NAME} && echo RESTART_OK"
    )
    result = run_remote(ssh_host, restart_script, ssh_key=ssh_key, timeout=15)
    if not result.success or "RESTART_OK" not in result.stdout:
        click.echo(click.style("  Restart failed", fg="red"))
        if result.stderr:
            click.echo(f"  {result.stderr[:200]}")
        raise SystemExit(1)
    click.echo(click.style("  Service restarted", fg="green"))

    # Step 5: Health check
    click.echo(f"Checking health at {brother.ember_host}:{ember_port}...")
    if check_ember_health_remote(brother.ember_host, ember_port):
        click.echo(click.style("  Ember is healthy!", fg="green"))
    else:
        click.echo(click.style("  Health check failed (may need a moment)", fg="yellow"))

    click.echo(click.style(f"\nEmber ({name}) deployed successfully!", fg="green", bold=True))


@deploy.command("all")
@click.option("--skip-build", is_flag=True, help="Skip frontend npm build")
@click.pass_context
def deploy_all(ctx: click.Context, skip_build: bool) -> None:
    """Deploy all components: hearth, frontend, conductor, ember."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    config = load_config_or_exit(config_dir)

    results: dict[str, bool] = {}

    # Hearth
    click.echo(click.style("=== Deploying Hearth ===", bold=True))
    try:
        ctx.invoke(hearth)
        results["hearth"] = True
    except SystemExit:
        results["hearth"] = False
        click.echo()

    # Frontend
    click.echo()
    click.echo(click.style("=== Deploying Frontend ===", bold=True))
    try:
        ctx.invoke(frontend, skip_build=skip_build)
        results["frontend"] = True
    except SystemExit:
        results["frontend"] = False
        click.echo()

    # Conductor
    click.echo()
    click.echo(click.style("=== Deploying Conductor ===", bold=True))
    try:
        ctx.invoke(conductor, personality=None, no_identity=False)
        results["conductor"] = True
    except SystemExit:
        results["conductor"] = False
        click.echo()

    # Ember — for each brother with ember_host
    ember_brothers = [n for n, b in config.brothers.items() if b.ember_host]
    for bro_name in ember_brothers:
        click.echo()
        click.echo(click.style(f"=== Deploying Ember ({bro_name}) ===", bold=True))
        try:
            ctx.invoke(ember, name=bro_name)
            results[f"ember:{bro_name}"] = True
        except SystemExit:
            results[f"ember:{bro_name}"] = False
            click.echo()

    # Summary
    click.echo()
    click.echo(click.style("=== Deploy Summary ===", bold=True))
    all_ok = True
    for component, ok in results.items():
        status = click.style("OK", fg="green") if ok else click.style("FAILED", fg="red")
        click.echo(f"  {component}: {status}")
        if not ok:
            all_ok = False

    if not all_ok:
        raise SystemExit(1)
