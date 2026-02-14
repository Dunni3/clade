#!/usr/bin/env bash
# One-time Tailscale setup for the cluster (no root required).
#
# Downloads the latest stable Tailscale static binary, places it in
# ~/.local/bin/tailscale/, creates state/socket directories, and runs
# a quick authentication test to verify everything works.
#
# Usage:
#   bash deploy/cluster-tailscale-setup.sh [--authkey tskey-auth-XXXXX]
#
# If --authkey is not provided, the script will check ~/.tailscale-authkey
# or prompt interactively.

set -euo pipefail

# --- Configuration ---
INSTALL_DIR="$HOME/.local/bin/tailscale"
STATE_DIR="$HOME/.local/share/tailscale"
AUTHKEY_FILE="$HOME/.tailscale-authkey"
TAILSCALE_VERSION="latest"  # Uses the latest stable release

# --- Parse arguments ---
AUTHKEY=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --authkey)
            AUTHKEY="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [--authkey tskey-auth-XXXXX]"
            exit 1
            ;;
    esac
done

# --- Resolve auth key ---
if [[ -z "$AUTHKEY" ]]; then
    if [[ -f "$AUTHKEY_FILE" ]]; then
        AUTHKEY=$(cat "$AUTHKEY_FILE")
        echo "==> Using auth key from $AUTHKEY_FILE"
    else
        echo "Enter your Tailscale auth key (generate at https://login.tailscale.com/admin/settings/keys):"
        read -r AUTHKEY
        if [[ -z "$AUTHKEY" ]]; then
            echo "Error: No auth key provided."
            exit 1
        fi
    fi
fi

# --- Save auth key ---
echo "==> Saving auth key to $AUTHKEY_FILE"
echo "$AUTHKEY" > "$AUTHKEY_FILE"
chmod 600 "$AUTHKEY_FILE"

# --- Create directories ---
echo "==> Creating directories"
mkdir -p "$INSTALL_DIR"
mkdir -p "$STATE_DIR"

# --- Download Tailscale ---
echo "==> Downloading latest stable Tailscale (linux amd64)..."
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Fetch the latest stable version number
LATEST_VERSION=$(curl -fsSL "https://pkgs.tailscale.com/stable/?mode=list" | grep -oP 'tailscale_\K[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -1)
if [[ -z "$LATEST_VERSION" ]]; then
    echo "Error: Could not determine latest Tailscale version."
    exit 1
fi
echo "    Version: $LATEST_VERSION"

TARBALL="tailscale_${LATEST_VERSION}_amd64.tgz"
DOWNLOAD_URL="https://pkgs.tailscale.com/stable/${TARBALL}"

curl -fsSL "$DOWNLOAD_URL" -o "$TMPDIR/$TARBALL"
tar -xzf "$TMPDIR/$TARBALL" -C "$TMPDIR"

# Copy binaries
EXTRACTED_DIR="$TMPDIR/tailscale_${LATEST_VERSION}_amd64"
cp "$EXTRACTED_DIR/tailscale" "$INSTALL_DIR/tailscale"
cp "$EXTRACTED_DIR/tailscaled" "$INSTALL_DIR/tailscaled"
chmod +x "$INSTALL_DIR/tailscale" "$INSTALL_DIR/tailscaled"

echo "==> Installed tailscale and tailscaled to $INSTALL_DIR"

# --- Verify binaries ---
echo "==> Verifying installation..."
"$INSTALL_DIR/tailscale" version
echo ""

# --- Quick authentication test ---
echo "==> Running authentication test..."
echo "    Starting tailscaled in userspace mode..."

"$INSTALL_DIR/tailscaled" \
    --tun=userspace-networking \
    --state="$STATE_DIR/tailscaled.state" \
    --socket="$STATE_DIR/tailscaled.sock" \
    --socks5-server=localhost:1055 \
    --outbound-http-proxy-listen=localhost:1056 &
DAEMON_PID=$!

# Give daemon time to start
sleep 3

if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "Error: tailscaled failed to start."
    exit 1
fi

echo "    Authenticating..."
"$INSTALL_DIR/tailscale" --socket="$STATE_DIR/tailscaled.sock" up --authkey="$AUTHKEY"

# Check status
echo "    Checking status..."
"$INSTALL_DIR/tailscale" --socket="$STATE_DIR/tailscaled.sock" status

TAILSCALE_IP=$("$INSTALL_DIR/tailscale" --socket="$STATE_DIR/tailscaled.sock" ip -4 2>/dev/null || echo "unknown")
echo ""
echo "==> Authentication test successful! Tailscale IP: $TAILSCALE_IP"

# --- Cleanup: shut down the test daemon ---
echo "==> Shutting down test daemon..."
"$INSTALL_DIR/tailscale" --socket="$STATE_DIR/tailscaled.sock" down 2>/dev/null || true
kill "$DAEMON_PID" 2>/dev/null || true
wait "$DAEMON_PID" 2>/dev/null || true

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "  Binaries:   $INSTALL_DIR/"
echo "  State:      $STATE_DIR/"
echo "  Auth key:   $AUTHKEY_FILE"
echo "  IP:         $TAILSCALE_IP"
echo ""
echo "  Next step: Submit the SLURM job to bring Tailscale online:"
echo "    bash deploy/cluster-tailscale-start.sh"
echo ""
