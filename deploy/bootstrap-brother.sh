#!/bin/bash
# Bootstrap a remote machine for clade brother setup.
#
# This script prepares a machine to be added as a clade brother by:
#   1. Detecting or installing miniforge3 (mamba/conda)
#   2. Creating a 'clade' conda environment with Python 3.11
#   3. Cloning the clade repo and pip-installing it
#   4. Verifying prerequisites (claude, tmux, git)
#
# Usage (run on the target machine):
#   curl -sSL https://raw.githubusercontent.com/dunni3/clade/main/deploy/bootstrap-brother.sh | bash
#
# Or from the coordinator:
#   clade bootstrap <ssh_host>
#
set -euo pipefail

CLADE_REPO="https://github.com/dunni3/clade.git"
CLADE_DIR="$HOME/.local/share/clade"
ENV_NAME="clade"
PYTHON_VERSION="3.11"

info()  { echo "==> $*"; }
ok()    { echo "  ✓ $*"; }
warn()  { echo "  ! $*"; }
fail()  { echo "  ✗ $*"; }

# ── Step 1: Detect or install conda/mamba ──────────────────────────
info "Checking for conda/mamba..."

CONDA=""
for candidate in mamba conda; do
    if command -v "$candidate" &>/dev/null; then
        CONDA="$candidate"
        break
    fi
done

# Check common install locations if not on PATH
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
    info "No conda/mamba found. Installing miniforge3..."
    INSTALLER="Miniforge3-$(uname)-$(uname -m).sh"
    INSTALLER_URL="https://github.com/conda-forge/miniforge/releases/latest/download/$INSTALLER"

    TMPDIR=$(mktemp -d)
    trap 'rm -rf "$TMPDIR"' EXIT

    curl -fsSL "$INSTALLER_URL" -o "$TMPDIR/$INSTALLER"
    bash "$TMPDIR/$INSTALLER" -b -p "$HOME/miniforge3"

    CONDA="$HOME/miniforge3/bin/mamba"
    export PATH="$HOME/miniforge3/bin:$PATH"
    ok "Miniforge3 installed at $HOME/miniforge3"
else
    ok "Found: $CONDA"
fi

# ── Step 2: Create conda env ───────────────────────────────────────
info "Checking for '$ENV_NAME' conda environment..."

# Use the conda binary to check env list
if "$CONDA" env list 2>/dev/null | grep -qE "(^|/)$ENV_NAME "; then
    ok "Environment '$ENV_NAME' already exists"
else
    info "Creating '$ENV_NAME' environment with Python $PYTHON_VERSION..."
    "$CONDA" create -n "$ENV_NAME" "python=$PYTHON_VERSION" -y -q
    ok "Environment '$ENV_NAME' created"
fi

# Find pip in the clade env
CLADE_PIP=""
for base in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/.conda"; do
    candidate="$base/envs/$ENV_NAME/bin/pip"
    if [ -x "$candidate" ]; then
        CLADE_PIP="$candidate"
        break
    fi
done

if [ -z "$CLADE_PIP" ]; then
    fail "Could not find pip in '$ENV_NAME' environment"
    exit 1
fi
ok "Pip: $CLADE_PIP"

# ── Step 3: Clone/update and install clade ─────────────────────────
info "Setting up clade package..."

if [ -d "$CLADE_DIR/.git" ]; then
    info "Updating existing clone at $CLADE_DIR..."
    git -C "$CLADE_DIR" pull --ff-only 2>/dev/null || git -C "$CLADE_DIR" fetch
    ok "Repository updated"
elif [ -f "$CLADE_DIR/pyproject.toml" ] 2>/dev/null; then
    # Exists but not a git repo (deployed via tar-pipe). Clone fresh.
    info "Replacing tar-pipe deploy with git clone..."
    rm -rf "$CLADE_DIR"
    git clone "$CLADE_REPO" "$CLADE_DIR"
    ok "Repository cloned"
else
    info "Cloning clade repository..."
    mkdir -p "$(dirname "$CLADE_DIR")"
    git clone "$CLADE_REPO" "$CLADE_DIR"
    ok "Repository cloned to $CLADE_DIR"
fi

info "Installing clade package..."
"$CLADE_PIP" install -e "$CLADE_DIR" -q 2>&1 | tail -3
ok "Clade installed"

# ── Step 4: Verify prerequisites ───────────────────────────────────
info "Checking prerequisites..."

MISSING=""

# Check clade entry points
CLADE_BIN_DIR="$(dirname "$CLADE_PIP")"
if [ -x "$CLADE_BIN_DIR/clade-worker" ]; then
    ok "clade-worker: $CLADE_BIN_DIR/clade-worker"
else
    fail "clade-worker not found"
    MISSING="$MISSING clade-worker"
fi
if [ -x "$CLADE_BIN_DIR/clade-ember" ]; then
    ok "clade-ember: $CLADE_BIN_DIR/clade-ember"
else
    fail "clade-ember not found"
    MISSING="$MISSING clade-ember"
fi

# Check claude
if command -v claude &>/dev/null; then
    ok "claude: $(command -v claude)"
else
    warn "claude: NOT FOUND (install Claude Code before adding as brother)"
    MISSING="$MISSING claude"
fi

# Check tmux
if command -v tmux &>/dev/null; then
    ok "tmux: $(command -v tmux)"
else
    warn "tmux: NOT FOUND (install with: sudo apt install tmux)"
    MISSING="$MISSING tmux"
fi

# Check git
if command -v git &>/dev/null; then
    ok "git: $(command -v git)"
else
    fail "git: NOT FOUND"
    MISSING="$MISSING git"
fi

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
if [ -z "$MISSING" ]; then
    echo "  Bootstrap complete! Ready for: clade add-brother"
else
    echo "  Bootstrap complete (with warnings)."
    echo "  Missing:$MISSING"
    echo ""
    echo "  Install missing tools, then run: clade add-brother"
fi
echo "════════════════════════════════════════════"
echo ""
echo "BOOTSTRAP_OK"
