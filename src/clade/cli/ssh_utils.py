"""SSH helpers for the Clade CLI.

Provides SSH connectivity testing, remote command execution, and
prerequisite checking for brother onboarding.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class SSHResult:
    """Result of an SSH operation."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    message: str = ""


def _build_ssh_cmd(host: str, ssh_key: str | None = None) -> list[str]:
    """Build base SSH command with common options."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    if ssh_key:
        cmd.extend(["-i", ssh_key])
    cmd.append(host)
    return cmd


def test_ssh(host: str, ssh_key: str | None = None) -> SSHResult:
    """Test SSH connectivity to a host.

    Args:
        host: SSH host string (e.g. 'ian@masuda').
        ssh_key: Optional path to SSH private key.

    Returns:
        SSHResult with success=True if connection works.
    """
    cmd = _build_ssh_cmd(host, ssh_key) + ["echo", "ok"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "ok" in result.stdout:
            return SSHResult(success=True, stdout=result.stdout, stderr=result.stderr)
        return SSHResult(
            success=False,
            stdout=result.stdout,
            stderr=result.stderr,
            message=f"SSH to {host} failed (exit {result.returncode})",
        )
    except subprocess.TimeoutExpired:
        return SSHResult(success=False, message=f"SSH to {host} timed out")
    except Exception as e:
        return SSHResult(success=False, message=f"SSH error: {e}")


def run_remote(
    host: str,
    script: str,
    ssh_key: str | None = None,
    timeout: int = 30,
) -> SSHResult:
    """Run a script on a remote host via SSH stdin.

    Args:
        host: SSH host string.
        script: Bash script content to execute.
        ssh_key: Optional path to SSH private key.
        timeout: Timeout in seconds.

    Returns:
        SSHResult with stdout/stderr from the remote execution.
    """
    cmd = _build_ssh_cmd(host, ssh_key) + ["bash", "-s"]
    try:
        result = subprocess.run(
            cmd, input=script, capture_output=True, text=True, timeout=timeout,
        )
        return SSHResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            message="" if result.returncode == 0 else f"Remote command failed (exit {result.returncode})",
        )
    except subprocess.TimeoutExpired:
        return SSHResult(success=False, message=f"Remote command on {host} timed out after {timeout}s")
    except Exception as e:
        return SSHResult(success=False, message=f"SSH error: {e}")


@dataclass
class RemotePrereqs:
    """Results of checking remote prerequisites."""

    python: str | None = None  # python binary path, or None if not found
    python_version: str | None = None
    claude: bool = False
    tmux: bool = False
    git: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return self.python is not None and self.claude and self.tmux and self.git


def deploy_clade_remote(host: str, ssh_key: str | None = None) -> SSHResult:
    """Clone/pull the clade repo and pip install on a remote host.

    Args:
        host: SSH host string (e.g. 'ian@masuda').
        ssh_key: Optional path to SSH private key.

    Returns:
        SSHResult — check for "DEPLOY_OK" in stdout for success.
    """
    script = """\
#!/bin/bash
set -e
CLADE_DIR="$HOME/.local/share/clade"

# If clade is already installed, just update it
if python3 -c "import clade" 2>/dev/null; then
    if [ -d "$CLADE_DIR/.git" ]; then
        cd "$CLADE_DIR"
        git pull --ff-only 2>&1 || true
        pip install -e . 2>&1 | tail -3
    fi
    echo "DEPLOY_OK"
    exit 0
fi

if [ -d "$CLADE_DIR/.git" ]; then
    cd "$CLADE_DIR"
    git pull --ff-only 2>&1
else
    git clone https://github.com/dunni3/clade.git "$CLADE_DIR" 2>&1
fi
cd "$CLADE_DIR"
pip install -e . 2>&1 | tail -3
echo "DEPLOY_OK"
"""
    return run_remote(host, script, ssh_key=ssh_key, timeout=120)


def check_remote_prereqs(host: str, ssh_key: str | None = None) -> RemotePrereqs:
    """Check that a remote host has the required tools installed.

    Checks for: python3 (3.10+), claude, tmux, git.

    Args:
        host: SSH host string.
        ssh_key: Optional SSH key path.

    Returns:
        RemotePrereqs with details about what's available.
    """
    script = """\
#!/bin/bash
# Check python
for py in python3.12 python3.11 python3.10 python3; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" --version 2>&1 | awk '{print $2}')
        echo "PYTHON:$(command -v $py):$ver"
        break
    fi
done

# Check claude
if command -v claude &>/dev/null; then
    echo "CLAUDE:yes"
else
    echo "CLAUDE:no"
fi

# Check tmux
if command -v tmux &>/dev/null; then
    echo "TMUX:yes"
else
    echo "TMUX:no"
fi

# Check git
if command -v git &>/dev/null; then
    echo "GIT:yes"
else
    echo "GIT:no"
fi
"""
    result = run_remote(host, script, ssh_key=ssh_key, timeout=15)
    prereqs = RemotePrereqs()

    if not result.success:
        prereqs.errors.append(f"SSH failed: {result.message}")
        return prereqs

    for line in result.stdout.strip().splitlines():
        if line.startswith("PYTHON:"):
            parts = line.split(":", 2)
            if len(parts) == 3:
                prereqs.python = parts[1]
                prereqs.python_version = parts[2]
        elif line.startswith("CLAUDE:"):
            prereqs.claude = line.split(":")[1] == "yes"
        elif line.startswith("TMUX:"):
            prereqs.tmux = line.split(":")[1] == "yes"
        elif line.startswith("GIT:"):
            prereqs.git = line.split(":")[1] == "yes"

    if prereqs.python is None:
        prereqs.errors.append("Python 3.10+ not found")
    if not prereqs.claude:
        prereqs.errors.append("Claude Code not found")
    if not prereqs.tmux:
        prereqs.errors.append("tmux not found")
    if not prereqs.git:
        prereqs.errors.append("git not found")

    return prereqs
