"""Context assembly for conductor ticks.

Builds the system prompt and user message for each tick based on
environment variables and the conductor-tick.md prompt file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


# Default location of the conductor tick prompt
DEFAULT_TICK_PROMPT_PATH = Path.home() / ".config" / "clade" / "conductor-tick.md"

# Fallback: bundled copy relative to this file (deploy/conductor-tick.md in the repo)
_REPO_TICK_PROMPT = Path(__file__).resolve().parent.parent.parent.parent / "deploy" / "conductor-tick.md"


def load_system_prompt(path: str | Path | None = None) -> str:
    """Load the conductor tick system prompt from file.

    Tries, in order:
        1. Explicit path argument
        2. CONDUCTOR_TICK_PROMPT env var
        3. ~/.config/clade/conductor-tick.md
        4. deploy/conductor-tick.md in the repo

    Raises FileNotFoundError if none are found.
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    env_path = os.environ.get("CONDUCTOR_TICK_PROMPT")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(DEFAULT_TICK_PROMPT_PATH)
    candidates.append(_REPO_TICK_PROMPT)

    for p in candidates:
        if p.exists():
            return p.read_text()

    raise FileNotFoundError(
        f"Conductor tick prompt not found. Searched: {[str(c) for c in candidates]}"
    )


def build_user_message() -> str:
    """Build the user message for a conductor tick.

    Includes:
        - Current UTC timestamp
        - Tick type (event-driven / message-driven / periodic)
        - TRIGGER_TASK_ID / TRIGGER_MESSAGE_ID values
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trigger_task_id = os.environ.get("TRIGGER_TASK_ID", "")
    trigger_message_id = os.environ.get("TRIGGER_MESSAGE_ID", "")

    lines = [f"Current time (UTC): {now}", ""]

    if trigger_task_id:
        lines.append(f"**Tick type: Event-driven** — triggered by task #{trigger_task_id}")
        lines.append(f"TRIGGER_TASK_ID={trigger_task_id}")
    elif trigger_message_id:
        lines.append(f"**Tick type: Message-driven** — triggered by message #{trigger_message_id}")
        lines.append(f"TRIGGER_MESSAGE_ID={trigger_message_id}")
    else:
        lines.append("**Tick type: Periodic** — routine timer tick")

    lines.append("")
    lines.append("Follow the instructions in your system prompt for this tick type.")

    return "\n".join(lines)
