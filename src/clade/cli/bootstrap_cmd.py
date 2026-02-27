"""clade bootstrap — prepare a remote machine for clade add-brother.

Creates a conda/mamba environment on the remote, deploys the clade package
via tar-pipe-SSH, and verifies prerequisites. After bootstrap, the machine
is ready for `clade add-brother`.
"""

from __future__ import annotations

import click

from .ssh_utils import SSHResult, run_remote, test_ssh


# Script that runs on the remote to detect/install conda and create the env.
# After this, deploy_clade_package() handles the actual code transfer + pip install.
BOOTSTRAP_ENV_SCRIPT = r"""#!/bin/bash
set -e

ENV_NAME="clade"
PYTHON_VERSION="3.11"

# ── Detect conda/mamba ──
CONDA=""
for candidate in mamba conda; do
    if command -v "$candidate" &>/dev/null; then
        CONDA="$candidate"
        break
    fi
done

# Check common install locations
if [ -z "$CONDA" ]; then
    for base in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3"; do
        if [ -x "$base/bin/mamba" ]; then
            CONDA="$base/bin/mamba"
            break
        elif [ -x "$base/bin/conda" ]; then
            CONDA="$base/bin/conda"
            break
        fi
    done
fi

if [ -z "$CONDA" ]; then
    echo "CONDA_MISSING"
    exit 0
fi

echo "CONDA_FOUND:$CONDA"

# ── Check/create env ──
if "$CONDA" env list 2>/dev/null | grep -qE "(^|/)$ENV_NAME "; then
    echo "ENV_EXISTS"
else
    echo "ENV_CREATING"
    "$CONDA" create -n "$ENV_NAME" "python=$PYTHON_VERSION" -y -q >/dev/null 2>&1
    echo "ENV_CREATED"
fi

# ── Find pip in the env ──
for base in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/.conda"; do
    candidate="$base/envs/$ENV_NAME/bin/pip"
    if [ -x "$candidate" ]; then
        echo "PIP_FOUND:$candidate"
        exit 0
    fi
done

echo "PIP_MISSING"
"""

INSTALL_CONDA_SCRIPT = r"""#!/bin/bash
set -e

echo "Installing miniforge3..."
INSTALLER="Miniforge3-$(uname)-$(uname -m).sh"
URL="https://github.com/conda-forge/miniforge/releases/latest/download/$INSTALLER"

TMPDIR=$(mktemp -d)
curl -fsSL "$URL" -o "$TMPDIR/$INSTALLER"
bash "$TMPDIR/$INSTALLER" -b -p "$HOME/miniforge3" >/dev/null 2>&1
rm -rf "$TMPDIR"

# Create clade env
"$HOME/miniforge3/bin/mamba" create -n clade python=3.11 -y -q >/dev/null 2>&1

# Find pip
PIP="$HOME/miniforge3/envs/clade/bin/pip"
if [ -x "$PIP" ]; then
    echo "PIP_FOUND:$PIP"
else
    echo "INSTALL_FAILED"
fi
"""

VERIFY_SCRIPT = r"""#!/bin/bash
# Check prerequisites after bootstrap

# Find clade-worker (prefer conda envs over ember-venv)
for d in \
    ~/miniforge3/envs/*/bin \
    ~/mambaforge/envs/*/bin \
    ~/miniconda3/envs/*/bin \
    ~/anaconda3/envs/*/bin \
    ~/.conda/envs/*/bin \
    ~/.local/ember-venv/bin; do
    if [ -x "$d/clade-worker" ]; then
        echo "CLADE_WORKER:$d/clade-worker"
        break
    fi
done

# Find clade-ember (prefer ember-venv over conda envs)
for d in \
    ~/.local/ember-venv/bin \
    ~/miniforge3/envs/*/bin \
    ~/mambaforge/envs/*/bin \
    ~/miniconda3/envs/*/bin \
    ~/anaconda3/envs/*/bin \
    ~/.conda/envs/*/bin; do
    if [ -x "$d/clade-ember" ]; then
        echo "CLADE_EMBER:$d/clade-ember"
        break
    fi
done

# Check other tools
if command -v claude &>/dev/null; then
    echo "CLAUDE:yes"
else
    echo "CLAUDE:no"
fi

if command -v tmux &>/dev/null; then
    echo "TMUX:yes"
else
    echo "TMUX:no"
fi

if command -v git &>/dev/null; then
    echo "GIT:yes"
else
    echo "GIT:no"
fi

echo "VERIFY_OK"
"""


@click.command("bootstrap")
@click.argument("ssh_host")
@click.option("--ssh-key", default=None, help="Path to SSH private key")
@click.option(
    "--install-conda/--no-install-conda",
    default=True,
    help="Auto-install miniforge3 if no conda/mamba found (default: yes)",
)
@click.option(
    "--ember-only",
    is_flag=True,
    default=False,
    help="Only set up the Ember venv (skip conda/dev environment)",
)
@click.pass_context
def bootstrap_cmd(
    ctx: click.Context,
    ssh_host: str,
    ssh_key: str | None,
    install_conda: bool,
    ember_only: bool,
) -> None:
    """Bootstrap a remote machine for clade add-brother.

    Ensures the remote has a conda/mamba environment with Python 3.11,
    deploys the clade package, and verifies prerequisites.

    With --ember-only, creates a dedicated venv for the Ember service
    instead of setting up a full conda environment. Use this when you
    only need the Ember server running (no dev environment).

    After bootstrap, run: clade add-brother --ssh SSH_HOST
    """
    click.echo(f"Bootstrapping {ssh_host}...")

    # Step 1: Test SSH
    click.echo("\n1. Testing SSH connectivity...")
    ssh_result = test_ssh(ssh_host, ssh_key=ssh_key)
    if not ssh_result.success:
        click.echo(click.style(f"   SSH failed: {ssh_result.message}", fg="red"))
        raise SystemExit(1)
    click.echo(click.style("   SSH OK", fg="green"))

    if ember_only:
        # Ember-only path: venv + non-editable install
        click.echo("\n2. Setting up Ember venv...")
        if not _setup_ember_venv(ssh_host, ssh_key):
            raise SystemExit(1)

        click.echo("\n3. Deploying clade package to ember venv...")
        _deploy_clade_ember_venv(ssh_host, ssh_key)
    else:
        # Standard path: conda env + editable install
        click.echo("\n2. Setting up conda environment...")
        pip_path = _setup_conda_env(ssh_host, ssh_key, install_conda)
        if not pip_path:
            raise SystemExit(1)

        click.echo("\n3. Deploying clade package...")
        _deploy_clade(ssh_host, ssh_key, pip_path)

    # Step 4: Verify
    click.echo("\n4. Verifying installation...")
    _verify(ssh_host, ssh_key)

    click.echo(
        click.style(
            f"\nBootstrap complete! Next step:\n  clade add-brother --ssh {ssh_host}",
            fg="green",
            bold=True,
        )
    )


def _setup_ember_venv(
    ssh_host: str,
    ssh_key: str | None,
) -> bool:
    """Create the Ember venv on the remote if it doesn't exist. Returns True on success."""
    script = r"""#!/bin/bash
set -e
VENV="$HOME/.local/ember-venv"

if [ -x "$VENV/bin/python" ]; then
    echo "VENV_EXISTS"
    echo "PIP:$VENV/bin/pip"
    exit 0
fi

PYBIN=""
for py in python3.12 python3.11 python3.10 python3; do
    command -v "$py" &>/dev/null && PYBIN="$py" && break
done

if [ -z "$PYBIN" ]; then
    echo "NO_PYTHON"
    exit 1
fi

echo "CREATING_VENV:$PYBIN"
"$PYBIN" -m venv "$VENV" 2>&1 || { echo "VENV_FAILED"; echo "Hint: sudo apt install python3-venv"; exit 1; }
echo "VENV_CREATED"
echo "PIP:$VENV/bin/pip"
"""
    result = run_remote(ssh_host, script, ssh_key=ssh_key, timeout=60)
    if not result.success:
        click.echo(click.style(f"   Failed: {result.message}", fg="red"))
        return False

    stdout = result.stdout
    for line in stdout.strip().splitlines():
        if line == "VENV_EXISTS":
            click.echo(click.style("   Ember venv already exists", fg="green"))
        elif line.startswith("CREATING_VENV:"):
            click.echo(f"   Creating venv with {line.split(':', 1)[1]}...")
        elif line == "VENV_CREATED":
            click.echo(click.style("   Ember venv created", fg="green"))
        elif line.startswith("PIP:"):
            click.echo(click.style(f"   Pip: {line.split(':', 1)[1]}", fg="green"))
        elif line == "NO_PYTHON":
            click.echo(click.style("   No python3 found on remote", fg="red"))
            return False
        elif line == "VENV_FAILED":
            click.echo(click.style("   Failed to create venv", fg="red"))
            click.echo("   Hint: sudo apt install python3-venv")
            return False

    return True


def _deploy_clade_ember_venv(ssh_host: str, ssh_key: str | None) -> None:
    """Deploy clade to the Ember venv via tar-pipe + non-editable install."""
    from .deploy_utils import deploy_clade_to_ember_venv

    result = deploy_clade_to_ember_venv(ssh_host, ssh_key=ssh_key)
    if result.success and "DEPLOY_OK" in result.stdout:
        click.echo(click.style("   Clade package installed in ember venv", fg="green"))
    else:
        click.echo(click.style(f"   Deploy failed: {result.message}", fg="red"))
        if result.stderr:
            click.echo(f"   {result.stderr[:300]}")
        raise SystemExit(1)


def _setup_conda_env(
    ssh_host: str,
    ssh_key: str | None,
    install_conda: bool,
) -> str | None:
    """Detect or create the conda env on the remote. Returns pip path or None."""
    result = run_remote(ssh_host, BOOTSTRAP_ENV_SCRIPT, ssh_key=ssh_key, timeout=60)
    if not result.success:
        click.echo(click.style(f"   Failed: {result.message}", fg="red"))
        return None

    stdout = result.stdout

    if "CONDA_MISSING" in stdout:
        if not install_conda:
            click.echo(click.style("   No conda/mamba found on remote", fg="red"))
            click.echo("   Install manually or re-run without --no-install-conda")
            return None

        click.echo("   No conda/mamba found. Installing miniforge3...")
        result = run_remote(ssh_host, INSTALL_CONDA_SCRIPT, ssh_key=ssh_key, timeout=300)
        if not result.success or "INSTALL_FAILED" in result.stdout:
            click.echo(click.style(f"   Miniforge3 installation failed", fg="red"))
            if result.stderr:
                click.echo(f"   {result.stderr[:300]}")
            return None
        stdout = result.stdout

    # Parse output
    for line in stdout.strip().splitlines():
        if line.startswith("CONDA_FOUND:"):
            click.echo(click.style(f"   Conda: {line.split(':', 1)[1]}", fg="green"))
        elif line == "ENV_EXISTS":
            click.echo(click.style("   Environment 'clade' already exists", fg="green"))
        elif line == "ENV_CREATING":
            click.echo("   Creating 'clade' environment...")
        elif line == "ENV_CREATED":
            click.echo(click.style("   Environment 'clade' created", fg="green"))
        elif line.startswith("PIP_FOUND:"):
            pip_path = line.split(":", 1)[1]
            click.echo(click.style(f"   Pip: {pip_path}", fg="green"))
            return pip_path
        elif line == "PIP_MISSING":
            click.echo(click.style("   Could not find pip in clade environment", fg="red"))
            return None

    click.echo(click.style("   Unexpected output from remote", fg="red"))
    return None


def _deploy_clade(ssh_host: str, ssh_key: str | None, pip_path: str) -> None:
    """Deploy the clade package via tar-pipe and install with the given pip."""
    from .deploy_utils import deploy_clade_package

    result = deploy_clade_package(ssh_host, ssh_key=ssh_key, pip_path=pip_path)
    if result.success and "DEPLOY_OK" in result.stdout:
        click.echo(click.style("   Clade package installed", fg="green"))
    else:
        click.echo(click.style(f"   Deploy failed: {result.message}", fg="red"))
        if result.stderr:
            click.echo(f"   {result.stderr[:300]}")
        raise SystemExit(1)


def _verify(ssh_host: str, ssh_key: str | None) -> None:
    """Verify that clade tools and prerequisites are available."""
    result = run_remote(ssh_host, VERIFY_SCRIPT, ssh_key=ssh_key, timeout=15)
    if not result.success:
        click.echo(click.style(f"   Verification failed: {result.message}", fg="yellow"))
        return

    warnings = []
    for line in result.stdout.strip().splitlines():
        if line.startswith("CLADE_WORKER:"):
            click.echo(click.style(f"   clade-worker: {line.split(':', 1)[1]}", fg="green"))
        elif line.startswith("CLADE_EMBER:"):
            click.echo(click.style(f"   clade-ember: {line.split(':', 1)[1]}", fg="green"))
        elif line == "CLAUDE:yes":
            click.echo(click.style("   claude: OK", fg="green"))
        elif line == "CLAUDE:no":
            warnings.append("claude (install Claude Code)")
            click.echo(click.style("   claude: NOT FOUND", fg="yellow"))
        elif line == "TMUX:yes":
            click.echo(click.style("   tmux: OK", fg="green"))
        elif line == "TMUX:no":
            warnings.append("tmux (sudo apt install tmux)")
            click.echo(click.style("   tmux: NOT FOUND", fg="yellow"))
        elif line == "GIT:yes":
            click.echo(click.style("   git: OK", fg="green"))
        elif line == "GIT:no":
            warnings.append("git")
            click.echo(click.style("   git: NOT FOUND", fg="yellow"))

    if warnings:
        click.echo(click.style(f"\n   Missing tools: {', '.join(warnings)}", fg="yellow"))
        click.echo("   Install these before running clade add-brother")
