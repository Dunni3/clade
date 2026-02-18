#!/usr/bin/env bash
# Conductor tick — runs Kamaji's periodic check-in.
# Called by systemd timer or cron every 15 minutes.

set -euo pipefail

CONFIG_DIR="${HOME}/.config/clade"
LOG_DIR="${HOME}/.local/share/clade/conductor-logs"
TICK_PROMPT="${CONFIG_DIR}/conductor-tick.md"
ENV_FILE="${CONFIG_DIR}/conductor.env"

# Concurrency guard — only one tick at a time
LOCK_FILE="${CONFIG_DIR}/conductor-tick.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "Conductor tick already running, skipping."
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

claude -p "$(cat "$TICK_PROMPT")" \
    --dangerously-skip-permissions \
    --max-turns 20 \
    --mcp-config "${HOME}/.config/clade/conductor-mcp.json" \
    2>&1 | tee -a "$LOG_FILE"

echo "=== Tick complete: $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG_FILE"

# Trim old logs (keep last 7 days)
find "$LOG_DIR" -name "tick_*.log" -mtime +7 -delete 2>/dev/null || true
