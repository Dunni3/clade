"""clade setup-github — install the Hearth-PR bridge workflow on a GitHub repo."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import click

from .clade_config import default_config_path, load_clade_config
from .keys import add_key, keys_path, load_keys


def _check_gh_cli() -> tuple[bool, str]:
    """Check that gh CLI is installed and authenticated.

    Returns:
        (ok, message) — ok is True if gh is ready to use.
    """
    if not shutil.which("gh"):
        return False, "gh CLI not found. Install from https://cli.github.com/"

    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, f"gh CLI not authenticated. Run 'gh auth login' first.\n{result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "gh auth status timed out"
    except Exception as e:
        return False, f"Error checking gh auth: {e}"

    return True, "ok"


def _detect_github_repo() -> tuple[str, str] | None:
    """Detect owner/repo from git remote origin.

    Returns:
        (owner, repo) tuple, or None if not a GitHub repo.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
    except Exception:
        return None

    url = result.stdout.strip()

    # SSH: git@github.com:owner/repo.git
    m = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)

    # HTTPS: https://github.com/owner/repo[.git]
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)

    return None


def _get_git_root() -> Path | None:
    """Get the git repository root directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


def _set_github_secret(owner_repo: str, name: str, value: str) -> bool:
    """Set a GitHub repository secret via gh CLI.

    Args:
        owner_repo: "owner/repo" string.
        name: Secret name.
        value: Secret value.

    Returns:
        True on success.
    """
    try:
        result = subprocess.run(
            ["gh", "secret", "set", name, "--repo", owner_repo],
            input=value,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


@click.command()
@click.option(
    "--no-verify-ssl",
    is_flag=True,
    help="Skip SSL verification for self-signed certs",
)
@click.pass_context
def setup_github_cmd(ctx: click.Context, no_verify_ssl: bool) -> None:
    """Install the Hearth-PR bridge workflow on the current GitHub repo."""
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None

    # Load config
    config = load_clade_config(default_config_path(config_dir))
    if config is None:
        click.echo(click.style("No clade.yaml found. Run 'clade init' first.", fg="red"), err=True)
        raise SystemExit(1)

    if not config.server_url:
        click.echo(click.style("No Hearth server URL configured in clade.yaml.", fg="red"), err=True)
        raise SystemExit(1)

    # Check gh CLI
    gh_ok, gh_msg = _check_gh_cli()
    if not gh_ok:
        click.echo(click.style(gh_msg, fg="red"), err=True)
        raise SystemExit(1)

    # Detect repo
    repo_info = _detect_github_repo()
    if repo_info is None:
        click.echo(
            click.style(
                "Could not detect a GitHub repo from git remote origin.\n"
                "Expected SSH (git@github.com:owner/repo.git) or HTTPS (https://github.com/owner/repo) format.",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)

    owner, repo = repo_info
    owner_repo = f"{owner}/{repo}"
    click.echo(f"Detected repo: {owner_repo}")

    # Find git root
    git_root = _get_git_root()
    if git_root is None:
        click.echo(click.style("Could not determine git root directory.", fg="red"), err=True)
        raise SystemExit(1)

    # Generate API key for this repo
    key_name = f"github-actions-{owner}-{repo}"
    kp = keys_path(config_dir)
    existing_keys = load_keys(kp)

    if key_name in existing_keys:
        api_key = existing_keys[key_name]
        click.echo(f"Using existing API key '{key_name}'")
    else:
        api_key = add_key(key_name, kp)
        click.echo(f"Generated API key '{key_name}' saved to {kp}")

    # Register key with Hearth
    if config.server_url:
        _register_key(config, api_key, key_name, kp, no_verify_ssl)

    # Set GitHub secrets
    click.echo(f"Setting GitHub repo secrets on {owner_repo}...")

    if _set_github_secret(owner_repo, "HEARTH_URL", config.server_url):
        click.echo(click.style("  HEARTH_URL set", fg="green"))
    else:
        click.echo(click.style("  Warning: failed to set HEARTH_URL secret", fg="yellow"))

    if _set_github_secret(owner_repo, "HEARTH_API_KEY", api_key):
        click.echo(click.style("  HEARTH_API_KEY set", fg="green"))
    else:
        click.echo(click.style("  Warning: failed to set HEARTH_API_KEY secret", fg="yellow"))

    # Write workflow file
    from ..templates import render_template

    workflow_content = render_template("hearth-bridge.yml")
    workflow_dir = git_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = workflow_dir / "hearth-bridge.yml"
    workflow_path.write_text(workflow_content)
    click.echo(f"Workflow written to {workflow_path}")

    # Summary
    click.echo()
    click.echo(click.style("Done!", fg="green", bold=True))
    click.echo("Next steps:")
    click.echo(f"  1. Review {workflow_path.relative_to(git_root)}")
    click.echo("  2. Commit and push to enable the workflow")


def _register_key(
    config,
    api_key: str,
    key_name: str,
    kp: Path,
    no_verify_ssl: bool,
) -> None:
    """Register the generated API key with the Hearth."""
    from ..communication.mailbox_client import MailboxClient

    keys = load_keys(kp)
    personal_key = keys.get(config.personal_name)
    if not personal_key:
        click.echo(
            click.style(
                f"  Warning: no API key found for '{config.personal_name}' — cannot register with Hearth",
                fg="yellow",
            )
        )
        return

    verify_ssl = not no_verify_ssl and config.server_url.startswith("https")
    client = MailboxClient(config.server_url, personal_key, verify_ssl=verify_ssl)
    try:
        ok = client.register_key_sync(key_name, api_key)
        if ok:
            click.echo(f"Registered '{key_name}' key with the Hearth")
        else:
            click.echo(click.style("  Warning: failed to register key with Hearth", fg="yellow"))
    except Exception as e:
        click.echo(click.style(f"  Warning: could not reach Hearth: {e}", fg="yellow"))
