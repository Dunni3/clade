#!/usr/bin/env bash
#SBATCH --job-name=jerry-ember
#SBATCH --partition=dept_cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=24:00:00
#SBATCH --output=jerry-ember-%j.log
#
# SLURM job that boots Tailscale in userspace mode and starts clade-ember.
# While running, Jerry is reachable on the tailnet and can receive tasks
# from the Hearth. No root privileges required.
#
# Prerequisites:
#   - Tailscale binaries installed via deploy/cluster-tailscale-setup.sh
#   - Auth key in ~/.config/clade/tailscale.env (TS_AUTHKEY=tskey-auth-XXX)
#   - Ember config in ~/.config/clade/ember.env (HEARTH_URL, HEARTH_API_KEY, etc.)
#   - clade-ember binary at ~/.conda/envs/clade/bin/clade-ember
#
# Usage:
#   sbatch deploy/jerry-ember.sbatch

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INSTALL_DIR="$HOME/.local/bin/tailscale"
TAILSCALE="$INSTALL_DIR/tailscale"
TAILSCALED="$INSTALL_DIR/tailscaled"
TS_SOCKET="/tmp/tailscaled-${SLURM_JOB_ID}.sock"

CLADE_EMBER="$HOME/.conda/envs/clade/bin/clade-ember"
EMBER_PORT="${EMBER_PORT:-8100}"

TS_ENV_FILE="$HOME/.config/clade/tailscale.env"
EMBER_ENV_FILE="$HOME/.config/clade/ember.env"

# ---------------------------------------------------------------------------
# Source environment files
# ---------------------------------------------------------------------------
if [[ -f "$TS_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$TS_ENV_FILE"
else
    echo "Error: Tailscale env file not found at $TS_ENV_FILE"
    echo "Expected contents: TS_AUTHKEY=tskey-auth-XXXXX"
    exit 1
fi

if [[ -f "$EMBER_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$EMBER_ENV_FILE"
else
    echo "Error: Ember env file not found at $EMBER_ENV_FILE"
    echo "Expected contents: HEARTH_URL, HEARTH_API_KEY, etc."
    exit 1
fi

# ---------------------------------------------------------------------------
# Validate required variables
# ---------------------------------------------------------------------------
: "${TS_AUTHKEY:?TS_AUTHKEY not set — add it to $TS_ENV_FILE}"
: "${HEARTH_URL:?HEARTH_URL not set — add it to $EMBER_ENV_FILE}"
: "${HEARTH_API_KEY:?HEARTH_API_KEY not set — add it to $EMBER_ENV_FILE}"

# Defaults for ember config
export HEARTH_NAME="${HEARTH_NAME:-jerry}"
export EMBER_BROTHER_NAME="${EMBER_BROTHER_NAME:-jerry}"
export EMBER_WORKING_DIR="${EMBER_WORKING_DIR:-/net/galaxy/home/koes/icd3/moldiff/OMTRA}"

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
if [[ ! -x "$TAILSCALED" ]]; then
    echo "Error: tailscaled not found at $TAILSCALED"
    echo "Run: bash deploy/cluster-tailscale-setup.sh"
    exit 1
fi

if [[ ! -x "$CLADE_EMBER" ]]; then
    echo "Error: clade-ember not found at $CLADE_EMBER"
    exit 1
fi

# ---------------------------------------------------------------------------
# Cleanup trap
# ---------------------------------------------------------------------------
TAILSCALED_PID=""
EMBER_PID=""

cleanup() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaning up..."

    # Notify Hearth that Jerry is going offline
    if [[ -n "${HEARTH_URL:-}" && -n "${HEARTH_API_KEY:-}" ]]; then
        curl -sf -X POST \
            "${HEARTH_URL}/api/v1/embers/${EMBER_BROTHER_NAME}/offline" \
            -H "Authorization: Bearer ${HEARTH_API_KEY}" \
            -H "Content-Type: application/json" \
            2>/dev/null || true
    fi

    # Stop Ember
    if [[ -n "$EMBER_PID" ]] && kill -0 "$EMBER_PID" 2>/dev/null; then
        kill "$EMBER_PID" 2>/dev/null || true
        wait "$EMBER_PID" 2>/dev/null || true
    fi

    # Disconnect Tailscale
    if [[ -S "$TS_SOCKET" ]]; then
        "$TAILSCALE" --socket="$TS_SOCKET" logout 2>/dev/null || true
    fi

    # Stop tailscaled
    if [[ -n "$TAILSCALED_PID" ]] && kill -0 "$TAILSCALED_PID" 2>/dev/null; then
        kill "$TAILSCALED_PID" 2>/dev/null || true
        wait "$TAILSCALED_PID" 2>/dev/null || true
    fi

    # Remove socket
    rm -f "$TS_SOCKET"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleanup complete."
}

trap cleanup EXIT SIGTERM SIGINT

# ---------------------------------------------------------------------------
# 1. Start tailscaled (userspace networking, ephemeral state)
# ---------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting tailscaled on $(hostname)..."
echo "  SLURM Job ID: $SLURM_JOB_ID"
echo "  Node: $(hostname)"

"$TAILSCALED" \
    --tun=userspace-networking \
    --state=mem: \
    --socket="$TS_SOCKET" \
    --port=0 &
TAILSCALED_PID=$!

# ---------------------------------------------------------------------------
# 2. Wait for socket to appear
# ---------------------------------------------------------------------------
echo "Waiting for tailscaled socket..."
for i in $(seq 1 30); do
    if [[ -S "$TS_SOCKET" ]]; then
        echo "  Socket ready after ${i}s"
        break
    fi
    if ! kill -0 "$TAILSCALED_PID" 2>/dev/null; then
        echo "Error: tailscaled exited unexpectedly."
        exit 1
    fi
    sleep 1
done

if [[ ! -S "$TS_SOCKET" ]]; then
    echo "Error: tailscaled socket did not appear within 30s."
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Authenticate with Tailscale
# ---------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Authenticating with Tailscale..."
"$TAILSCALE" --socket="$TS_SOCKET" up \
    --authkey="$TS_AUTHKEY" \
    --hostname="jerry-slurm-${SLURM_JOB_ID}"

# ---------------------------------------------------------------------------
# 4. Discover Tailscale IP
# ---------------------------------------------------------------------------
TS_IP=$("$TAILSCALE" --socket="$TS_SOCKET" ip -4)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Tailscale IP: $TS_IP"

# ---------------------------------------------------------------------------
# 5. Wait for netstack stabilization
# ---------------------------------------------------------------------------
echo "Waiting for netstack to stabilize..."
sleep 3

# ---------------------------------------------------------------------------
# 6. Start clade-ember in background, then register with Hearth
# ---------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting clade-ember..."
"$CLADE_EMBER" &
EMBER_PID=$!

# Wait for Ember to become healthy
echo "Waiting for Ember health check..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${EMBER_PORT}/health" >/dev/null 2>&1; then
        echo "  Ember healthy after ${i}s"
        break
    fi
    if ! kill -0 "$EMBER_PID" 2>/dev/null; then
        echo "Error: clade-ember exited unexpectedly."
        exit 1
    fi
    sleep 1
done

if ! curl -sf "http://127.0.0.1:${EMBER_PORT}/health" >/dev/null 2>&1; then
    echo "Error: Ember did not become healthy within 30s."
    exit 1
fi

# ---------------------------------------------------------------------------
# 7. Register Jerry's Tailscale IP with Hearth
# ---------------------------------------------------------------------------
EMBER_URL="http://${TS_IP}:${EMBER_PORT}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Registering with Hearth: $EMBER_URL"

HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X PUT "${HEARTH_URL}/api/v1/embers/${EMBER_BROTHER_NAME}" \
    -H "Authorization: Bearer ${HEARTH_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"ember_url\": \"${EMBER_URL}\"}")

if [[ "$HTTP_CODE" == "200" ]]; then
    echo "  Registered successfully."
else
    echo "  Warning: Registration returned HTTP $HTTP_CODE (continuing anyway)."
fi

# ---------------------------------------------------------------------------
# 8. Report status
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  Jerry is online!"
echo "  Tailscale IP:  $TS_IP"
echo "  Ember URL:     $EMBER_URL"
echo "  Node:          $(hostname)"
echo "  SLURM Job ID:  $SLURM_JOB_ID"
echo "============================================"
echo ""

# ---------------------------------------------------------------------------
# 9. Keep alive — wait on Ember process
# ---------------------------------------------------------------------------
wait "$EMBER_PID"
EMBER_EXIT=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] clade-ember exited with code $EMBER_EXIT."
exit "$EMBER_EXIT"
