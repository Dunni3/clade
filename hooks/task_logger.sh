#!/bin/bash
# Hook script for logging Claude Code activity to the Hearth task events API.
#
# Designed to be registered as a PostToolUse / Stop hook in ~/.claude/settings.json.
# No-ops when CLAUDE_TASK_ID is not set, so it's safe to install globally —
# only task sessions launched via initiate_ssh_task will export the env vars.
#
# Required env vars (set by the task runner script):
#   CLAUDE_TASK_ID  - The task ID to log events against
#   HEARTH_URL      - Base URL of the Hearth API (e.g. https://54.84.119.14)
#   HEARTH_API_KEY  - API key for authentication
#   (Legacy fallback: MAILBOX_URL, MAILBOX_API_KEY also accepted)
#
# Receives hook context as JSON on stdin. See Claude Code hooks documentation.
#
# Dependencies: python3, curl (no jq needed)

[ -z "$CLAUDE_TASK_ID" ] && exit 0

# Support HEARTH_* with MAILBOX_* fallback
HEARTH_URL="${HEARTH_URL:-$MAILBOX_URL}"
HEARTH_API_KEY="${HEARTH_API_KEY:-$MAILBOX_API_KEY}"

[ -z "$HEARTH_URL" ] && exit 0
[ -z "$HEARTH_API_KEY" ] && exit 0

# Capture stdin (JSON from Claude Code hook system)
INPUT=$(cat)

# Parse JSON and build POST body using Python (avoids jq dependency)
POST_BODY=$(echo "$INPUT" | python3 -c "
import json, sys

data = json.load(sys.stdin)

event = data.get('hook_event_name', '')
tool = data.get('tool_name', '')
tool_input = data.get('tool_input', {})

if event == 'Stop':
    summary = 'Session ended'
elif not tool:
    summary = event
elif tool == 'Bash':
    summary = 'ran: ' + (tool_input.get('command', '') or '')[:200]
elif tool == 'Write':
    summary = 'wrote: ' + (tool_input.get('file_path', '') or '')
elif tool == 'Edit':
    summary = 'edited: ' + (tool_input.get('file_path', '') or '')
elif tool == 'Task':
    summary = 'subagent: ' + (tool_input.get('description', '') or '')
else:
    summary = tool

payload = {
    'event_type': event,
    'tool_name': tool if tool else None,
    'summary': summary,
}
print(json.dumps(payload))
" 2>/dev/null) || exit 0

[ -z "$POST_BODY" ] && exit 0

# POST to the task events API (fire-and-forget, don't block Claude)
curl -s --max-time 5 \
    -X POST "$HEARTH_URL/api/v1/tasks/$CLAUDE_TASK_ID/log" \
    -H "Authorization: Bearer $HEARTH_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$POST_BODY" > /dev/null 2>&1 &

exit 0
