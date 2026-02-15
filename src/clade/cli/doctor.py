"""clade doctor — run diagnostics on the Clade setup."""

from __future__ import annotations

from pathlib import Path

import click
import httpx

from .clade_config import default_config_path, load_clade_config
from .identity import MARKER_START
from .keys import keys_path, load_keys
from .mcp_utils import is_mcp_registered
from .ssh_utils import run_remote, test_ssh


def _pass(msg: str) -> None:
    click.echo(click.style("[PASS] ", fg="green") + msg)


def _fail(msg: str, fix: str | None = None) -> None:
    click.echo(click.style("[FAIL] ", fg="red") + msg)
    if fix:
        click.echo(f"       Fix: {fix}")


def _warn(msg: str) -> None:
    click.echo(click.style("[WARN] ", fg="yellow") + msg)


@click.command()
def doctor() -> None:
    """Run diagnostics on your Clade setup."""
    config_path = default_config_path()
    issues = 0

    # 1. Config file
    config = load_clade_config(config_path)
    if config is None:
        _fail(f"Config: {config_path} not found or invalid", fix="clade init")
        click.echo()
        click.echo("Run 'clade init' to create a configuration.")
        raise SystemExit(1)
    _pass(f"Config: {config_path}")

    # 2. Keys file
    kp = keys_path()
    keys = load_keys(kp)
    if keys:
        _pass(f"Keys: {kp} ({len(keys)} keys)")
    else:
        _fail(f"Keys: {kp} not found or empty", fix="clade init")
        issues += 1

    # 3. Personal MCP registered
    if is_mcp_registered("clade-personal"):
        _pass("Personal MCP: registered in ~/.claude.json")
    else:
        _fail("Personal MCP: not registered in ~/.claude.json", fix="clade init")
        issues += 1

    # 4. Personal API key
    if config.personal_name in keys:
        _pass(f"Personal key: '{config.personal_name}' has an API key")
    else:
        _fail(
            f"Personal key: '{config.personal_name}' missing from keys.json",
            fix="clade init",
        )
        issues += 1

    # 5. Personal identity in CLAUDE.md
    local_claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if local_claude_md.exists() and MARKER_START in local_claude_md.read_text():
        _pass("Personal identity: written in ~/.claude/CLAUDE.md")
    else:
        _warn("Personal identity: not found in ~/.claude/CLAUDE.md (run 'clade init' to write)")

    # 6. Server
    if config.server_url:
        if _check_server(config.server_url):
            _pass(f"Server: {config.server_url} responding")
        else:
            _fail(f"Server: {config.server_url} not responding")
            issues += 1
    else:
        _warn("Server: not configured (brothers can't communicate)")

    # 7. Each brother
    for name, bro in config.brothers.items():
        click.echo()
        click.echo(click.style(f"Brother: {name}", bold=True))

        # SSH
        ssh_result = test_ssh(bro.ssh)
        if ssh_result.success:
            _pass(f"SSH to {bro.ssh}")
        else:
            _fail(f"SSH to {bro.ssh}: {ssh_result.message}")
            issues += 1
            continue  # Can't check remote stuff without SSH

        # API key
        if name in keys:
            _pass(f"API key for '{name}'")
        else:
            _fail(f"No API key for '{name}'", fix=f"clade add-brother --name {name} --ssh {bro.ssh}")
            issues += 1

        # Clade package installed
        pkg_result = run_remote(bro.ssh, "python3 -c 'import clade; print(\"OK\")' 2>&1", timeout=15)
        if pkg_result.success and "OK" in pkg_result.stdout:
            _pass("Clade package installed")
        else:
            _fail("Clade package not installed on remote", fix=f"clade add-brother --name {name} --ssh {bro.ssh}")
            issues += 1

        # MCP registered on remote
        mcp_result = run_remote(
            bro.ssh,
            "python3 -c \"import json; d=json.load(open('$HOME/.claude.json')); print('clade-worker' in d.get('mcpServers',{}))\" 2>&1",
            timeout=15,
        )
        if mcp_result.success and "True" in mcp_result.stdout:
            _pass("MCP registered on remote")
        else:
            _fail("MCP not registered on remote", fix=f"clade add-brother --name {name} --ssh {bro.ssh}")
            issues += 1

        # Identity written on remote
        identity_result = run_remote(
            bro.ssh,
            "grep -c 'CLADE_IDENTITY_START' ~/.claude/CLAUDE.md 2>/dev/null || echo 0",
            timeout=15,
        )
        if identity_result.success and identity_result.stdout.strip() not in ("", "0"):
            _pass("Identity written on remote")
        else:
            _warn(f"Identity not found on remote (run 'clade add-brother --name {name} --ssh {bro.ssh}' to write)")

        # Can reach Hearth
        if config.server_url:
            hearth_result = run_remote(
                bro.ssh,
                f"python3 -c \"import urllib.request; r=urllib.request.urlopen('{config.server_url}/api/v1/health', timeout=5); print('HEARTH_OK' if r.status==200 else 'HEARTH_FAIL')\" 2>&1",
                timeout=20,
            )
            if hearth_result.success and "HEARTH_OK" in hearth_result.stdout:
                _pass(f"Can reach Hearth from {bro.ssh}")
            else:
                _fail(f"Cannot reach Hearth from {bro.ssh}")
                issues += 1

        # Ember server
        if bro.ember_host and bro.ember_port:
            # HTTP health check
            if _check_ember(bro.ember_host, bro.ember_port):
                _pass(f"Ember: http://{bro.ember_host}:{bro.ember_port}/health responding")
            else:
                _fail(f"Ember: http://{bro.ember_host}:{bro.ember_port}/health not responding")
                issues += 1

            # systemd service check via SSH
            svc_result = run_remote(
                bro.ssh,
                "systemctl is-active clade-ember 2>/dev/null || echo inactive",
                timeout=10,
            )
            if svc_result.success and "active" == svc_result.stdout.strip():
                _pass("Ember service: active")
            else:
                status = svc_result.stdout.strip() if svc_result.success else "unknown"
                _warn(f"Ember service: {status}")

    # Summary
    click.echo()
    if issues == 0:
        click.echo(click.style("All checks passed!", fg="green", bold=True))
    else:
        click.echo(click.style(f"{issues} issue(s) found.", fg="red", bold=True))
    raise SystemExit(0 if issues == 0 else 1)


def _check_ember(host: str, port: int) -> bool:
    """Check if an Ember server is responding."""
    try:
        resp = httpx.get(f"http://{host}:{port}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _check_server(url: str) -> bool:
    """Check if the Hearth server is responding."""
    try:
        resp = httpx.get(f"{url}/api/v1/health", timeout=5, verify=False)
        return resp.status_code == 200
    except Exception:
        try:
            resp = httpx.get(url, timeout=5, verify=False)
            return resp.status_code in (200, 301, 302)
        except Exception:
            return False
