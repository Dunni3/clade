"""Context assembly for conductor ticks.

Builds the system prompt and user message for each tick based on
environment variables and the conductor-tick.md prompt file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import jinja2


TickType = Literal["periodic", "event", "message"]

_TEMPLATE_NAMES: dict[TickType, str] = {
    "periodic": "tick_periodic.md.j2",
    "event": "tick_event.md.j2",
    "message": "tick_message.md.j2",
}

# Default location of the conductor tick prompt (legacy monolithic file)
DEFAULT_TICK_PROMPT_PATH = Path.home() / ".config" / "clade" / "conductor-tick.md"

# Fallback: bundled copy relative to this file (deploy/conductor-tick.md in the repo)
_REPO_TICK_PROMPT = Path(__file__).resolve().parent.parent.parent.parent / "deploy" / "conductor-tick.md"

# Template directories: deployed location and repo location
DEFAULT_TICK_TEMPLATE_DIR = Path.home() / ".config" / "clade" / "conductor-tick"
_REPO_TICK_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "deploy" / "conductor-tick"


def detect_tick_type() -> TickType:
    """Detect the tick type from environment variables.

    Returns:
        "event" if TRIGGER_TASK_ID is set,
        "message" if TRIGGER_MESSAGE_ID is set,
        "periodic" otherwise.
    """
    if os.environ.get("TRIGGER_TASK_ID"):
        return "event"
    if os.environ.get("TRIGGER_MESSAGE_ID"):
        return "message"
    return "periodic"


def render_tick_prompt(tick_type: TickType, template_dir: Path | None = None) -> str:
    """Render the appropriate tick prompt template using Jinja2.

    Tries template directories in order:
        1. Explicit template_dir argument
        2. ~/.config/clade/conductor-tick/
        3. deploy/conductor-tick/ in the repo

    Args:
        tick_type: The tick type ("periodic", "event", or "message").
        template_dir: Optional explicit template directory to try first.

    Returns:
        Rendered prompt string.

    Raises:
        FileNotFoundError: If no matching template is found in any directory.
    """
    dirs_to_try: list[Path] = []
    if template_dir:
        dirs_to_try.append(template_dir)
    dirs_to_try += [DEFAULT_TICK_TEMPLATE_DIR, _REPO_TICK_TEMPLATE_DIR]

    template_name = _TEMPLATE_NAMES[tick_type]

    for tdir in dirs_to_try:
        template_file = tdir / template_name
        if template_file.exists():
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(tdir)),
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
            )
            return env.get_template(template_name).render()

    raise FileNotFoundError(
        f"No template found for tick type '{tick_type}' (looked for '{template_name}'). "
        f"Searched: {[str(d) for d in dirs_to_try]}"
    )


def load_system_prompt(path: str | Path | None = None) -> str:
    """Load the conductor tick system prompt.

    Tries, in order:
        1. Explicit path argument (legacy monolithic file)
        2. CONDUCTOR_TICK_PROMPT env var (legacy monolithic file)
        3. Template rendering: detect tick type, render per-type Jinja2 template
           from ~/.config/clade/conductor-tick/ or deploy/conductor-tick/ in repo
        4. ~/.config/clade/conductor-tick.md (legacy monolithic fallback)
        5. deploy/conductor-tick.md in the repo (legacy monolithic fallback)

    Raises FileNotFoundError if none are found.
    """
    # 1. Explicit path argument
    if path:
        p = Path(path)
        if p.exists():
            return p.read_text()

    # 2. CONDUCTOR_TICK_PROMPT env var
    env_path = os.environ.get("CONDUCTOR_TICK_PROMPT")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p.read_text()

    # 3. Template rendering
    tick_type = detect_tick_type()
    try:
        return render_tick_prompt(tick_type)
    except FileNotFoundError:
        pass

    # 4 & 5. Legacy monolithic fallbacks
    for fallback in (DEFAULT_TICK_PROMPT_PATH, _REPO_TICK_PROMPT):
        if fallback.exists():
            return fallback.read_text()

    raise FileNotFoundError(
        "Conductor tick prompt not found. No templates or monolithic prompt file available."
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
