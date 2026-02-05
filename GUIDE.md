# Terminal Spawner — Build Guide

## What This Is

An MCP (Model Context Protocol) server that gives Doot (Claude Code on Ian's local Mac) the ability to open new iTerm2 terminal windows. The main use case is spawning SSH sessions to connect with Brother Oppy (masuda) and Brother Jerry (cluster).

When Ian says "I need to talk to Jerry," Doot calls the `connect_to_brother` tool and an iTerm2 window pops up with an SSH session to the cluster running Claude Code.

## Architecture

Four files, flat layout, no packages:

```
terminal-spawner/
├── CLAUDE.md       # Original spec / vision document
├── GUIDE.md        # This file
├── pyproject.toml  # Project metadata + dependencies
├── server.py       # MCP server entry point (FastMCP, two tools)
├── terminal.py     # AppleScript generation + execution
└── brothers.py     # Brother configurations (hardcoded)
```

### server.py

Defines the FastMCP server with two tools:

- **`spawn_terminal(command?, app?)`** — Opens a new terminal window. Optionally runs a command in it. Defaults to iTerm2 but can use Terminal.app.
- **`connect_to_brother(name)`** — Shortcut for connecting to "jerry" or "oppy". Looks up the SSH command from `brothers.py` and calls `spawn_terminal` under the hood.

### terminal.py

Two functions:

- `generate_applescript(command, app)` — Builds an AppleScript string for either iTerm2 or Terminal.app. If no command is given, just opens an empty window.
- `run_applescript(script)` — Executes the script via `osascript -e` and returns "OK" or an error message.

### brothers.py

A simple dictionary mapping brother names to their SSH commands:

- **jerry**: `ssh -t cluster "claude"`
- **oppy**: `ssh -t masuda "cd ~/projects/mol_diffusion/OMTRA_oppy && claude"`

### Transport

The server uses **stdio** transport (standard for local MCP servers running as subprocesses of Claude Code).

## Environment Setup

### Prerequisites

- macOS with conda (`~/opt/miniconda3`)
- iTerm2 installed (for default terminal support)

### Creating the Environment

```bash
# Create conda env with Python 3.12
conda create -n terminal-spawner python=3.12 -y

# Activate it
conda activate terminal-spawner

# Install uv (fast Python package installer) via conda
conda install -c conda-forge uv -y

# Install the MCP dependency
uv pip install "mcp[cli]"
```

### Key Details

- **Conda env name:** `terminal-spawner`
- **Python path:** `/Users/iandunn/opt/miniconda3/envs/terminal-spawner/bin/python`
- **Python version:** 3.12
- **Main dependency:** `mcp[cli]` (which brings in FastMCP, pydantic, etc.)
- **uv** is installed via conda inside the env for fast dependency management

## Registration with Claude Code

The server is registered at **user scope** (available in all projects):

```bash
claude mcp add --scope user --transport stdio terminal-spawner -- \
  /Users/iandunn/opt/miniconda3/envs/terminal-spawner/bin/python \
  /Users/iandunn/projects/terminal-spawner/server.py
```

This writes to `~/.claude.json`. The entry uses the full absolute path to the conda env's Python so it doesn't depend on which env is active when Claude Code starts.

## Running

### As an MCP Server (normal usage)

Claude Code launches it automatically as a subprocess. After registering, restart Claude Code and the tools appear. Verify with `/mcp`.

### Standalone (for testing)

```bash
conda activate terminal-spawner
cd ~/projects/terminal-spawner
python server.py
```

This starts the server on stdio and waits for input. It won't do anything visible since it expects MCP protocol messages, but if it doesn't crash, the server is healthy.

### Quick import test

```bash
conda activate terminal-spawner
python -c "import sys; sys.path.insert(0, '.'); from server import mcp; print('OK')"
```

## Usage Examples

Once registered and Claude Code is restarted, just talk naturally:

| What you say | What Doot does |
|---|---|
| "Open a session with Jerry" | `connect_to_brother(name="jerry")` |
| "I need to talk to Oppy" | `connect_to_brother(name="oppy")` |
| "Spawn me a terminal" | `spawn_terminal()` |
| "Open a terminal and run `htop`" | `spawn_terminal(command="htop")` |
| "Open a Terminal.app window" | `spawn_terminal(app="terminal")` |

## How It Works Under the Hood

1. Doot decides to call `connect_to_brother("jerry")`
2. `server.py` looks up jerry's config in `brothers.py`
3. `terminal.py` generates an AppleScript that tells iTerm2 to create a new window and write the SSH command
4. `osascript -e` executes the AppleScript
5. iTerm2 window appears on screen with the SSH session
6. Doot returns a confirmation message: "Opened session with Brother Jerry — GPU jobs on the cluster"

## Future Ideas

- Window tracking (know which sessions are open)
- Cross-instance messaging
- Task delegation (`claude -p "prompt"` for non-interactive tasks)
- Status checking (is a brother's session still active?)

---

*Built by Doot, February 5, 2026*
