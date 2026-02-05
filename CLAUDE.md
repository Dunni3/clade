# Terminal Spawner MCP Server

## Vision

An MCP tool that lets Doot (Claude Code on Ian's local macOS laptop) spawn new terminal windows, particularly to connect with Brother Oppy (masuda) and Brother Jerry (cluster).

The goal: Ian says "hey Doot, I need to talk to Jerry" and a terminal window pops up with an SSH session to cluster running Claude Code.

## The Problem

Claude Code's Bash tool runs commands and returns output, but can't create interactive sessions that Ian can take over. We need a bridge between Doot's world (non-interactive command execution) and Ian's world (interactive terminal sessions).

## Core Functionality

### 1. Spawn Terminal Window
Open a new terminal window (Terminal.app or iTerm2) and optionally run a command in it.

```
spawn_terminal(command?: string, app?: "terminal" | "iterm2")
```

### 2. Connect to Family Members
Predefined shortcuts for connecting to other Claude Code instances:

```
connect_to_brother(name: "jerry" | "oppy", initial_prompt?: string)
```

**Jerry (cluster):**
```bash
ssh -t cluster "claude"
```

**Oppy (masuda):**
```bash
ssh -t masuda "cd ~/projects/mol_diffusion/OMTRA_oppy && claude"
```

### 3. Delegate Task (Stretch Goal)
Spawn a session AND send an initial prompt/task. This is trickier - might need to:
- Use `claude -p "prompt"` for non-interactive single tasks
- Or figure out how to send keystrokes to the new window

## Technical Approach

### AppleScript Core
macOS lets us script terminal apps via AppleScript:

**Terminal.app:**
```applescript
tell application "Terminal"
    activate
    do script "ssh -t cluster 'claude'"
end tell
```

**iTerm2:**
```applescript
tell application "iTerm2"
    create window with default profile
    tell current session of current window
        write text "ssh -t cluster 'claude'"
    end tell
end tell
```

### MCP Server Structure

```
terminal-spawner/
├── CLAUDE.md           # This file
├── package.json
├── src/
│   ├── index.ts        # MCP server entry point
│   ├── terminal.ts     # AppleScript execution logic
│   └── brothers.ts     # Family member configurations
└── dist/               # Compiled output
```

### Configuration

The server should be configurable. Store brother definitions in a config:

```json
{
  "terminal_app": "iterm2",
  "brothers": {
    "jerry": {
      "host": "cluster",
      "working_dir": null,
      "description": "Brother Jerry - GPU jobs and real results"
    },
    "oppy": {
      "host": "masuda",
      "working_dir": "~/projects/mol_diffusion/OMTRA_oppy",
      "description": "Brother Oppy - The architect"
    }
  }
}
```

## Open Questions

1. **TypeScript or Python?**
   - TS is more common for MCP servers, better ecosystem support
   - Python might be simpler, Ian is more familiar with it
   - Leaning TS for alignment with MCP conventions

2. **How to handle initial prompts?**
   - `claude -p "prompt"` runs non-interactively and exits
   - Could paste text into terminal after spawning, but timing is tricky
   - Maybe a two-step flow: spawn, then "send message to window"?

3. **Window management?**
   - Should we track spawned windows?
   - Could assign names/IDs to reference them later
   - "Send this to the Jerry window I opened earlier"

4. **Error handling?**
   - What if SSH fails?
   - What if the terminal app isn't installed?
   - Doot won't see the terminal output, so errors are invisible

5. **Security considerations?**
   - Executing arbitrary commands in new terminals
   - Should we restrict to predefined commands/hosts?

## MVP Scope

For v0.1, keep it simple:

1. Single tool: `spawn_terminal`
   - Takes optional `command` string
   - Takes optional `app` preference (default to user's preferred terminal)

2. Single tool: `connect_to_brother`
   - Takes `name` (jerry or oppy)
   - Opens SSH + Claude Code session

3. Hardcoded config (no external config file yet)

4. No window tracking, no message passing, no delegation

## Future Ideas

- **Cross-instance communication**: A way for Doot to send messages to Oppy/Jerry's sessions
- **Status checking**: Query if a brother's session is still active
- **Task queue**: Doot queues up tasks, Jerry picks them up when ready
- **Shared context**: Sync relevant context between instances

## Installation (Future)

```bash
# In this directory
npm install
npm run build

# Register with Claude Code
# Add to ~/.claude/mcp.json:
{
  "mcpServers": {
    "terminal-spawner": {
      "command": "node",
      "args": ["/Users/iandunn/projects/terminal-spawner/dist/index.js"]
    }
  }
}
```

## Usage Examples (Future)

**Ian:** "Doot, open a terminal to Jerry"
**Doot:** *calls connect_to_brother("jerry")*
*New iTerm2 window opens with SSH to cluster + Claude Code*

**Ian:** "Doot, I need Oppy to review the training script"
**Doot:** *calls connect_to_brother("oppy")*
"I've opened a session with Brother Oppy. You can ask him to review the training script."

**Ian:** "Spawn me a terminal on masuda, I need to check something manually"
**Doot:** *calls spawn_terminal("ssh masuda")*

---

*Document created by Doot, February 5, 2026*
*For future Doot, Oppy, Jerry, and Ian to build upon*
