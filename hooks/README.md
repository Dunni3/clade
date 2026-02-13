# Task Logger Hook

Automatically logs Claude Code activity to the Hearth task events API during SSH task sessions.

## Setup

1. Copy `task_logger.sh` to `~/.claude/hooks/` on the brother's machine:
   ```bash
   mkdir -p ~/.claude/hooks
   cp hooks/task_logger.sh ~/.claude/hooks/task_logger.sh
   chmod +x ~/.claude/hooks/task_logger.sh
   ```

2. Add hook configuration to `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Bash|Edit|Write|Task",
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/task_logger.sh",
               "timeout": 10
             }
           ]
         }
       ],
       "Stop": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "~/.claude/hooks/task_logger.sh",
               "timeout": 10
             }
           ]
         }
       ]
     }
   }
   ```

3. Requires `python3` and `curl` on the brother's machine.

## How it works

- The hook script checks for `CLAUDE_TASK_ID` env var — if not set, it exits immediately (no-op)
- Only task sessions launched via `initiate_ssh_task` set the required env vars
- Normal interactive Claude Code sessions are completely unaffected
- Events are POSTed asynchronously (backgrounded curl) so they don't slow down the session
- Supports `HEARTH_URL`/`HEARTH_API_KEY` env vars with `MAILBOX_URL`/`MAILBOX_API_KEY` fallback
