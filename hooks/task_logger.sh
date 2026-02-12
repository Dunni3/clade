#!/bin/bash
# Hook script for logging Claude Code activity to the mailbox task events API.
#
# Designed to be registered as a PostToolUse / Stop hook in ~/.claude/settings.json.
# No-ops when CLAUDE_TASK_ID is not set, so it's safe to install globally —
# only task sessions launched via initiate_ssh_task will export the env vars.
#
# Required env vars (set by the task runner script):
#   CLAUDE_TASK_ID  - The task ID to log events against
#   MAILBOX_URL     - Base URL of the mailbox API (e.g. https://54.84.119.14)
#   MAILBOX_API_KEY - API key for authentication
#
# Receives hook context as JSON on stdin. See Claude Code hooks documentation.

[ -z "$CLAUDE_TASK_ID" ] && exit 0
[ -z "$MAILBOX_URL" ] && exit 0
[ -z "$MAILBOX_API_KEY" ] && exit 0

# Read JSON from stdin
INPUT=$(cat)

EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // empty')
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Build a human-readable summary based on event type
if [ "$EVENT" = "Stop" ]; then
    SUMMARY="Session ended"
elif [ -z "$TOOL" ]; then
    SUMMARY="$EVENT"
elif [ "$TOOL" = "Bash" ]; then
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' | head -c 200)
    SUMMARY="ran: $CMD"
elif [ "$TOOL" = "Write" ]; then
    FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
    SUMMARY="wrote: $FILE"
elif [ "$TOOL" = "Edit" ]; then
    FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
    SUMMARY="edited: $FILE"
elif [ "$TOOL" = "Task" ]; then
    DESC=$(echo "$INPUT" | jq -r '.tool_input.description // empty')
    SUMMARY="subagent: $DESC"
else
    SUMMARY="$TOOL"
fi

# POST to the task events API (fire-and-forget, don't block Claude)
curl -s --max-time 5 \
    -X POST "$MAILBOX_URL/api/v1/tasks/$CLAUDE_TASK_ID/log" \
    -H "Authorization: Bearer $MAILBOX_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
        --arg event_type "$EVENT" \
        --arg tool_name "$TOOL" \
        --arg summary "$SUMMARY" \
        '{event_type: $event_type, tool_name: (if $tool_name == "" then null else $tool_name end), summary: $summary}'
    )" > /dev/null 2>&1 &

exit 0
