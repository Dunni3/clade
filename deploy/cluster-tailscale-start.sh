#!/usr/bin/env bash
# Submit the Tailscale SLURM job and report the Tailscale IP once it's up.
#
# Usage:
#   bash deploy/cluster-tailscale-start.sh
#
# Options:
#   --stop    Cancel the running Tailscale job instead of starting one

set -euo pipefail

# --- Configuration ---
STATE_DIR="$HOME/.local/share/tailscale"
JOB_NAME="tailscale"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOB_SCRIPT="$SCRIPT_DIR/cluster-tailscale-job.sh"

# --- Functions ---
get_running_job() {
    squeue --me --name="$JOB_NAME" --noheader --format="%i" 2>/dev/null | head -1
}

stop_tailscale() {
    local job_id
    job_id=$(get_running_job)
    if [[ -n "$job_id" ]]; then
        echo "Cancelling Tailscale job $job_id..."
        scancel "$job_id"
        rm -f "$STATE_DIR/current-ip"
        echo "Done. Jerry is offline."
    else
        echo "No running Tailscale job found."
    fi
    exit 0
}

# --- Parse arguments ---
case "${1:-}" in
    --stop)
        stop_tailscale
        ;;
    --help|-h)
        echo "Usage: $0 [--stop]"
        echo ""
        echo "  (no args)   Submit the Tailscale SLURM job"
        echo "  --stop      Cancel the running Tailscale job"
        exit 0
        ;;
esac

# --- Check for existing job ---
EXISTING_JOB=$(get_running_job)
if [[ -n "$EXISTING_JOB" ]]; then
    echo "Tailscale job is already running (Job ID: $EXISTING_JOB)"
    if [[ -f "$STATE_DIR/current-ip" ]]; then
        echo "Tailscale IP: $(cat "$STATE_DIR/current-ip")"
    fi
    echo ""
    echo "To restart, first cancel the existing job:"
    echo "  $0 --stop"
    exit 0
fi

# --- Preflight checks ---
if [[ ! -f "$JOB_SCRIPT" ]]; then
    echo "Error: Job script not found at $JOB_SCRIPT"
    exit 1
fi

if [[ ! -x "$HOME/.local/bin/tailscale/tailscaled" ]]; then
    echo "Error: Tailscale not installed. Run the setup script first:"
    echo "  bash deploy/cluster-tailscale-setup.sh"
    exit 1
fi

if [[ ! -f "$HOME/.tailscale-authkey" ]]; then
    echo "Error: Auth key not found at ~/.tailscale-authkey"
    echo "Run the setup script first."
    exit 1
fi

# --- Submit job ---
echo "Submitting Tailscale SLURM job..."
JOB_ID=$(sbatch --parsable "$JOB_SCRIPT")
echo "Job submitted: $JOB_ID"
echo ""

# --- Wait for Tailscale to come online ---
echo "Waiting for Tailscale to authenticate..."
IP_FILE="$STATE_DIR/current-ip"
rm -f "$IP_FILE"

MAX_WAIT=120  # seconds
ELAPSED=0
while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    # Check job is still running
    JOB_STATE=$(squeue --job="$JOB_ID" --noheader --format="%t" 2>/dev/null || echo "")
    if [[ -z "$JOB_STATE" ]]; then
        echo ""
        echo "Error: Job $JOB_ID is no longer in the queue."
        echo "Check the log file for details: tailscale-${JOB_ID}.log"
        exit 1
    fi

    if [[ "$JOB_STATE" == "PD" ]]; then
        printf "\r  Job is pending (queued)... %ds" "$ELAPSED"
    elif [[ -f "$IP_FILE" ]]; then
        TAILSCALE_IP=$(cat "$IP_FILE")
        echo ""
        echo ""
        echo "============================================"
        echo "  Jerry is online!"
        echo "  Tailscale IP: $TAILSCALE_IP"
        echo "  SLURM Job:   $JOB_ID"
        echo "============================================"
        echo ""
        echo "To stop:  $0 --stop"
        echo "To check: squeue --me --name=$JOB_NAME"
        exit 0
    else
        printf "\r  Job is running, waiting for Tailscale IP... %ds" "$ELAPSED"
    fi

    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

echo ""
echo ""
echo "Timed out waiting for Tailscale IP after ${MAX_WAIT}s."
echo "The job ($JOB_ID) may still be starting. Check:"
echo "  squeue --me --name=$JOB_NAME"
echo "  cat tailscale-${JOB_ID}.log"
exit 1
