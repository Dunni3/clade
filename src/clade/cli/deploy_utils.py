"""Shared deploy helpers for `clade deploy` subcommands.

Provides tar-pipe-SSH file transfer (no git dependency), config loading,
and clade package deployment.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from .clade_config import CladeConfig, default_config_path, load_clade_config
from .ssh_utils import SSHResult, _build_ssh_cmd, run_remote


def load_config_or_exit(config_dir: Path | None) -> CladeConfig:
    """Load clade.yaml or exit with error."""
    config_path = default_config_path(config_dir)
    config = load_clade_config(config_path)
    if config is None:
        click.echo("No clade.yaml found. Run 'clade init' first.", err=True)
        raise SystemExit(1)
    return config


def require_server_ssh(config: CladeConfig) -> tuple[str, str | None]:
    """Validate server SSH config and return (ssh_host, ssh_key).

    Exits with error if server.ssh is not configured.
    """
    if not config.server_ssh:
        click.echo(
            click.style("No server SSH configured in clade.yaml", fg="red"),
            err=True,
        )
        click.echo("Set server.ssh in clade.yaml or run 'clade init' with --server-ssh", err=True)
        raise SystemExit(1)
    return config.server_ssh, config.server_ssh_key


def scp_directory(
    local_dir: str | Path,
    ssh_host: str,
    remote_dir: str,
    ssh_key: str | None = None,
    exclude: list[str] | None = None,
    timeout: int = 60,
) -> SSHResult:
    """Copy a local directory to a remote path via tar pipe + sudo.

    Uses `tar -cf - | ssh sudo tar -xf -` for root-owned targets.
    Creates the remote directory if it doesn't exist.

    Args:
        local_dir: Local directory to copy.
        ssh_host: SSH host string.
        remote_dir: Absolute remote directory path.
        ssh_key: Optional SSH key path.
        exclude: List of patterns to exclude from tar.
        timeout: Timeout in seconds.

    Returns:
        SSHResult with success/failure.
    """
    local_path = Path(local_dir)
    if not local_path.is_dir():
        return SSHResult(
            success=False,
            message=f"Local directory not found: {local_dir}",
        )

    # Build tar command
    tar_cmd = ["tar", "-cf", "-", "-C", str(local_path.parent), local_path.name]
    for pattern in (exclude or []):
        tar_cmd.insert(1, f"--exclude={pattern}")

    # Build SSH command
    ssh_cmd = _build_ssh_cmd(ssh_host, ssh_key)
    ssh_cmd.extend([
        "sudo", "mkdir", "-p", remote_dir, "&&",
        "sudo", "tar", "-xf", "-", "-C", remote_dir,
        "--strip-components=1",
    ])

    try:
        tar_proc = subprocess.Popen(
            tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        ssh_proc = subprocess.Popen(
            ssh_cmd,
            stdin=tar_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tar_proc.stdout.close()  # Allow tar_proc to receive SIGPIPE
        stdout, stderr = ssh_proc.communicate(timeout=timeout)
        tar_proc.wait(timeout=5)

        success = ssh_proc.returncode == 0
        return SSHResult(
            success=success,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            message="" if success else f"scp_directory failed (exit {ssh_proc.returncode})",
        )
    except subprocess.TimeoutExpired:
        for p in [tar_proc, ssh_proc]:
            try:
                p.kill()
            except Exception:
                pass
        return SSHResult(success=False, message=f"scp_directory timed out after {timeout}s")
    except Exception as e:
        return SSHResult(success=False, message=f"scp_directory error: {e}")


def scp_build_directory(
    local_dir: str | Path,
    ssh_host: str,
    remote_dir: str,
    ssh_key: str | None = None,
    owner: str = "www-data",
    timeout: int = 60,
) -> SSHResult:
    """Copy a local directory to a remote path via /tmp staging + sudo cp + chown.

    For deploying to non-root-owned directories (e.g., /var/www/hearth/).
    Stages through /tmp first, then sudo copies and chowns.

    Args:
        local_dir: Local directory to copy.
        ssh_host: SSH host string.
        remote_dir: Absolute remote directory path.
        ssh_key: Optional SSH key path.
        owner: Owner for the remote files.
        timeout: Timeout in seconds.

    Returns:
        SSHResult with success/failure.
    """
    local_path = Path(local_dir)
    if not local_path.is_dir():
        return SSHResult(
            success=False,
            message=f"Local directory not found: {local_dir}",
        )

    staging_dir = "/tmp/clade-deploy-staging"

    # Build tar command
    tar_cmd = ["tar", "-cf", "-", "-C", str(local_path.parent), local_path.name]

    # Build SSH command: stage to /tmp, then sudo cp + chown
    # Pass as a single argument — SSH concatenates remote args with spaces,
    # so "bash -c <multi-word>" breaks (only first word becomes the script).
    ssh_cmd = _build_ssh_cmd(ssh_host, ssh_key)
    ssh_cmd.append(
        f"rm -rf {staging_dir} && mkdir -p {staging_dir} && "
        f"tar -xf - -C {staging_dir} --strip-components=1 && "
        f"sudo rm -rf {remote_dir}/* && "
        f"sudo mkdir -p {remote_dir} && "
        f"sudo cp -r {staging_dir}/* {remote_dir}/ && "
        f"sudo chown -R {owner}:{owner} {remote_dir}/ && "
        f"rm -rf {staging_dir} && echo SCP_BUILD_OK"
    )

    try:
        tar_proc = subprocess.Popen(
            tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        ssh_proc = subprocess.Popen(
            ssh_cmd,
            stdin=tar_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tar_proc.stdout.close()
        stdout, stderr = ssh_proc.communicate(timeout=timeout)
        tar_proc.wait(timeout=5)

        stdout_str = stdout.decode(errors="replace")
        stderr_str = stderr.decode(errors="replace")
        success = ssh_proc.returncode == 0 and "SCP_BUILD_OK" in stdout_str

        return SSHResult(
            success=success,
            stdout=stdout_str,
            stderr=stderr_str,
            message="" if success else f"scp_build_directory failed (exit {ssh_proc.returncode})",
        )
    except subprocess.TimeoutExpired:
        for p in [tar_proc, ssh_proc]:
            try:
                p.kill()
            except Exception:
                pass
        return SSHResult(success=False, message=f"scp_build_directory timed out after {timeout}s")
    except Exception as e:
        return SSHResult(success=False, message=f"scp_build_directory error: {e}")


def deploy_clade_package(
    ssh_host: str,
    ssh_key: str | None = None,
    timeout: int = 120,
) -> SSHResult:
    """Deploy the clade package to a remote host via tar pipe + pip install.

    Two-step process:
    1. Tar the local clade project (excluding .git, node_modules, etc),
       pipe to ~/.local/share/clade/ on remote via tar | ssh tar.
    2. Run pip install -e . via run_remote.

    Finds the right pip by searching for one that already has clade installed.

    Args:
        ssh_host: SSH host string.
        ssh_key: Optional SSH key path.
        timeout: Timeout in seconds.

    Returns:
        SSHResult — check for "DEPLOY_OK" in stdout for success.
    """
    # Find the clade project root (this file is at src/clade/cli/deploy_utils.py)
    project_root = Path(__file__).resolve().parent.parent.parent.parent

    if not (project_root / "pyproject.toml").exists():
        return SSHResult(
            success=False,
            message=f"Could not find clade project root (expected pyproject.toml at {project_root})",
        )

    # Step 1: Transfer files via tar pipe
    excludes = [
        ".git", "node_modules", "frontend/node_modules", "frontend/dist",
        "__pycache__", "*.egg-info", ".pytest_cache", "research_notes",
        ".DS_Store", "docker",
    ]
    tar_cmd = ["tar", "-cf", "-", "-C", str(project_root.parent), project_root.name]
    for pattern in excludes:
        tar_cmd.insert(1, f"--exclude={pattern}")

    clade_dir = "~/.local/share/clade"
    ssh_cmd = _build_ssh_cmd(ssh_host, ssh_key)
    ssh_cmd.append(
        f"mkdir -p {clade_dir} && tar -xf - -C {clade_dir} --strip-components=1"
    )

    try:
        tar_proc = subprocess.Popen(
            tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        ssh_proc = subprocess.Popen(
            ssh_cmd,
            stdin=tar_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tar_proc.stdout.close()
        stdout, stderr = ssh_proc.communicate(timeout=timeout)
        tar_proc.wait(timeout=5)

        if ssh_proc.returncode != 0:
            return SSHResult(
                success=False,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                message=f"File transfer failed (exit {ssh_proc.returncode})",
            )
    except subprocess.TimeoutExpired:
        for p in [tar_proc, ssh_proc]:
            try:
                p.kill()
            except Exception:
                pass
        return SSHResult(success=False, message=f"File transfer timed out after {timeout}s")
    except Exception as e:
        return SSHResult(success=False, message=f"File transfer error: {e}")

    # Step 2: Find pip and install
    install_script = """\
#!/bin/bash
set -e
CLADE_DIR="$HOME/.local/share/clade"

# Find pip that has clade installed
PIP=""
for candidate in \\
    ~/mambaforge/envs/*/bin/pip \\
    ~/miniforge3/envs/*/bin/pip \\
    ~/miniconda3/envs/*/bin/pip \\
    ~/anaconda3/envs/*/bin/pip \\
    ~/.conda/envs/*/bin/pip \\
    ~/.local/venv/bin/pip \\
    ~/.local/bin/pip; do
    if [ -x "$candidate" ]; then
        if "$candidate" show clade >/dev/null 2>&1; then
            PIP="$candidate"
            break
        fi
    fi
done

# Fallback: try system pip
if [ -z "$PIP" ]; then
    for candidate in pip3 pip; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PIP="$(command -v $candidate)"
            break
        fi
    done
fi

if [ -z "$PIP" ]; then
    echo "ERROR: No pip found on remote"
    exit 1
fi

echo "Using pip: $PIP"
cd "$CLADE_DIR"
"$PIP" install -e . 2>&1 | tail -5
echo "DEPLOY_OK"
"""
    return run_remote(ssh_host, install_script, ssh_key=ssh_key, timeout=timeout)
