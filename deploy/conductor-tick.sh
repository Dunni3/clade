#!/usr/bin/env bash
# Conductor tick — runs Kamaji's periodic check-in.
# Called by systemd timer or cron every 15 minutes.
#
# Usage:
#   conductor-tick.sh                  # periodic tick
#   conductor-tick.sh <task_id>        # event-driven (task completed/failed)
#   conductor-tick.sh --message <id>   # event-driven (message to kamaji)

set -euo pipefail

TRIGGER_TASK_ID=""
TRIGGER_MESSAGE_ID=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --message)
            TRIGGER_MESSAGE_ID="${2:-}"
            shift 2
            ;;
        *)
            TRIGGER_TASK_ID="$1"
            shift
            ;;
    esac
done

CONFIG_DIR="${HOME}/.config/clade"
LOG_DIR="${HOME}/.local/share/clade/conductor-logs"
TICK_PROMPT="${CONFIG_DIR}/conductor-tick.md"
ENV_FILE="${CONFIG_DIR}/conductor.env"

# Concurrency guard — only one tick at a time, others queue (up to 10 min)
LOCK_FILE="${CONFIG_DIR}/conductor-tick.lock"
exec 200>"$LOCK_FILE"
if ! flock -w 600 200; then
    echo "Conductor tick: could not acquire lock after 10 min, skipping."
    exit 0
fi

# Source environment
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Ensure log directory exists
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/tick_${TIMESTAMP}.log"

# Run the tick
echo "=== Conductor tick: $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee "$LOG_FILE"
if [[ -n "$TRIGGER_TASK_ID" ]]; then
    echo "  Triggered by task #${TRIGGER_TASK_ID}" | tee -a "$LOG_FILE"
elif [[ -n "$TRIGGER_MESSAGE_ID" ]]; then
    echo "  Triggered by message #${TRIGGER_MESSAGE_ID}" | tee -a "$LOG_FILE"
fi

env ${TRIGGER_TASK_ID:+TRIGGER_TASK_ID=$TRIGGER_TASK_ID} \
    ${TRIGGER_MESSAGE_ID:+TRIGGER_MESSAGE_ID=$TRIGGER_MESSAGE_ID} \
    claude -p "$(cat "$TICK_PROMPT")" \
    --dangerously-skip-permissions \
    --max-turns 20 \
    --mcp-config "${HOME}/.config/clade/conductor-mcp.json" \
    2>&1 | tee -a "$LOG_FILE"

echo "=== Tick complete: $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG_FILE"

# Trim old logs (keep last 7 days)
find "$LOG_DIR" -name "tick_*.log" -mtime +7 -delete 2>/dev/null || true
