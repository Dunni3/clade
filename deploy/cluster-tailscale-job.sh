#!/usr/bin/env bash
#SBATCH --job-name=tailscale
#SBATCH --partition=dept_cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=512M
#SBATCH --time=24:00:00
#SBATCH --output=%x-%j.log
#
# SLURM job that runs Tailscale in userspace networking mode.
# No root privileges required.
#
# This job keeps Tailscale connected for the duration of the SLURM
# allocation (default 24 hours). When the job ends or is cancelled,
# Tailscale is cleanly shut down via a SIGTERM trap.
#
# Usage:
#   sbatch deploy/cluster-tailscale-job.sh
#
# Or use the helper script:
#   bash deploy/cluster-tailscale-start.sh

set -euo pipefail

# --- Configuration ---
INSTALL_DIR="$HOME/.local/bin/tailscale"
STATE_DIR="$HOME/.local/share/tailscale"
AUTHKEY_FILE="$HOME/.tailscale-authkey"
LOG_DIR="$HOME/.local/share/tailscale/logs"
SOCKS5_PORT=1055
HTTP_PROXY_PORT=1056

TAILSCALE="$INSTALL_DIR/tailscale"
TAILSCALED="$INSTALL_DIR/tailscaled"
SOCKET="$STATE_DIR/tailscaled.sock"
STATE="$STATE_DIR/tailscaled.state"

# --- Preflight checks ---
if [[ ! -x "$TAILSCALED" ]]; then
    echo "Error: tailscaled not found at $TAILSCALED"
    echo "Run the setup script first: bash deploy/cluster-tailscale-setup.sh"
    exit 1
fi

if [[ ! -f "$AUTHKEY_FILE" ]]; then
    echo "Error: Auth key file not found at $AUTHKEY_FILE"
    echo "Run the setup script first: bash deploy/cluster-tailscale-setup.sh"
    exit 1
fi

AUTHKEY=$(cat "$AUTHKEY_FILE")
if [[ -z "$AUTHKEY" ]]; then
    echo "Error: Auth key file is empty."
    exit 1
fi

# --- Create log directory ---
mkdir -p "$LOG_DIR"

# --- Cleanup function ---
DAEMON_PID=""
cleanup() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Shutting down Tailscale..."
    if [[ -S "$SOCKET" ]]; then
        "$TAILSCALE" --socket="$SOCKET" down 2>/dev/null || true
    fi
    if [[ -n "$DAEMON_PID" ]] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        kill "$DAEMON_PID" 2>/dev/null || true
        wait "$DAEMON_PID" 2>/dev/null || true
    fi
    # Clean up socket file
    rm -f "$SOCKET"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Tailscale shut down cleanly."
}

# Trap signals for clean shutdown (SIGTERM from SLURM, SIGINT, EXIT)
trap cleanup SIGTERM SIGINT EXIT

# --- Start tailscaled ---
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting tailscaled on $(hostname)..."
echo "  SLURM Job ID: ${SLURM_JOB_ID:-N/A}"
echo "  Node: $(hostname)"
echo "  SOCKS5 proxy: localhost:$SOCKS5_PORT"
echo "  HTTP proxy:   localhost:$HTTP_PROXY_PORT"
echo ""

"$TAILSCALED" \
    --tun=userspace-networking \
    --state="$STATE" \
    --socket="$SOCKET" \
    --socks5-server="localhost:$SOCKS5_PORT" \
    --outbound-http-proxy-listen="localhost:$HTTP_PROXY_PORT" &
DAEMON_PID=$!

# Give daemon time to start
sleep 3

if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "Error: tailscaled failed to start."
    exit 1
fi

# --- Authenticate ---
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Authenticating with Tailscale..."
"$TAILSCALE" --socket="$SOCKET" up --authkey="$AUTHKEY"

# --- Report status ---
echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Tailscale is online."
"$TAILSCALE" --socket="$SOCKET" status
TAILSCALE_IP=$("$TAILSCALE" --socket="$SOCKET" ip -4 2>/dev/null || echo "unknown")
echo ""
echo "============================================"
echo "  Jerry is online!"
echo "  Tailscale IP: $TAILSCALE_IP"
echo "  Node:         $(hostname)"
echo "  Job ID:       ${SLURM_JOB_ID:-N/A}"
echo "============================================"
echo ""

# Write IP to a known file so the start script can read it
echo "$TAILSCALE_IP" > "$STATE_DIR/current-ip"

# --- Keep alive ---
# The job stays running as long as tailscaled is alive.
# Periodic health checks log status every 30 minutes.
while kill -0 "$DAEMON_PID" 2>/dev/null; do
    sleep 1800  # 30 minutes
    if kill -0 "$DAEMON_PID" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Health check: tailscaled running (PID $DAEMON_PID)"
        "$TAILSCALE" --socket="$SOCKET" status 2>/dev/null || echo "  (status check failed)"
    fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] tailscaled exited unexpectedly."
exit 1
