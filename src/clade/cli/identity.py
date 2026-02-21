"""Identity section generation and CLAUDE.md management for Clade brothers."""

from __future__ import annotations

import base64
from pathlib import Path

from .ssh_utils import SSHResult, run_remote

MARKER_START = "<!-- CLADE_IDENTITY_START -->"
MARKER_END = "<!-- CLADE_IDENTITY_END -->"


def generate_personal_identity(
    name: str,
    clade_name: str,
    personality: str = "",
    brothers: dict[str, dict] | None = None,
) -> str:
    """Generate a CLAUDE.md identity section for the personal coordinator.

    Args:
        name: The personal brother's name.
        clade_name: Name of the clade.
        personality: Optional personality description.
        brothers: Dict of brother names to info dicts (with 'role', 'description' keys).

    Returns:
        Markdown string wrapped in identity markers.
    """
    lines = [
        MARKER_START,
        f"# {clade_name} — Identity",
        "",
        f"**Name:** {name}",
        f"**Role:** Personal coordinator",
        "",
    ]

    if personality:
        lines.append(f"**Personality:** {personality}")
    else:
        lines.append("**Personality:** No personality description provided.")
    lines.append("")

    # MCP tools
    lines.append("## Available Tools (clade-personal)")
    lines.append("")
    lines.append("- `list_brothers` — List available brother instances")
    lines.append("- `send_message` — Send a message via the Hearth")
    lines.append("- `check_mailbox` — Check for messages")
    lines.append("- `read_message` — Read a specific message")
    lines.append("- `browse_feed` — Browse all messages")
    lines.append("- `unread_count` — Get unread message count")
    lines.append("- `list_tasks` — List tasks from the Hearth")
    lines.append("- `get_task` — Get task details")
    lines.append("- `update_task` — Update task status")
    lines.append("- `initiate_ssh_task` — Delegate a task to a brother via SSH")
    lines.append("- `deposit_morsel` — Deposit a note/observation (linkable to tasks, brothers, cards)")
    lines.append("- `list_morsels` — List morsels (filter by creator, tag, task_id, card_id)")
    lines.append("- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board (cards support links to tasks, morsels, trees, messages, other cards)")
    lines.append("")

    # Brothers
    if brothers:
        lines.append("## Brothers")
        lines.append("")
        for bro_name, bro_info in brothers.items():
            desc = bro_info.get("description", "")
            role = bro_info.get("role", "worker")
            entry = f"- **{bro_name}** ({role})"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)
        lines.append("")

    lines.append(MARKER_END)
    return "\n".join(lines)


def generate_conductor_identity(
    name: str,
    clade_name: str,
    personality: str = "",
    workers: dict[str, dict] | None = None,
    brothers: dict[str, dict] | None = None,
) -> str:
    """Generate a CLAUDE.md identity section for the conductor.

    Args:
        name: The conductor's name.
        clade_name: Name of the clade.
        personality: Optional personality description.
        workers: Dict of worker names to info dicts (managed by this conductor).
        brothers: Dict of all brother names to info dicts.

    Returns:
        Markdown string wrapped in identity markers.
    """
    lines = [
        MARKER_START,
        f"# {clade_name} — Identity",
        "",
        f"**Name:** {name}",
        f"**Role:** Conductor",
        "",
    ]

    if personality:
        lines.append(f"**Personality:** {personality}")
    else:
        lines.append("**Personality:** No personality description provided.")
    lines.append("")

    # MCP tools
    lines.append("## Available Tools (clade-conductor)")
    lines.append("")
    lines.append("- `send_message` — Send a message via the Hearth")
    lines.append("- `check_mailbox` — Check for messages")
    lines.append("- `read_message` — Read a specific message")
    lines.append("- `browse_feed` — Browse all messages")
    lines.append("- `unread_count` — Get unread message count")
    lines.append("- `list_tasks` — List tasks from the Hearth")
    lines.append("- `get_task` — Get task details")
    lines.append("- `update_task` — Update task status")
    lines.append("- `delegate_task` — Delegate a task to a worker via Ember")
    lines.append("- `check_worker_health` — Check worker Ember health")
    lines.append("- `list_worker_tasks` — List active worker tasks")
    lines.append("- `deposit_morsel` — Deposit a note/observation (linkable to tasks, brothers, cards)")
    lines.append("- `list_morsels` — List morsels (filter by creator, tag, task_id, card_id)")
    lines.append("- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board (cards support links to tasks, morsels, trees, messages, other cards)")
    lines.append("")

    # Workers
    if workers:
        lines.append("## Workers")
        lines.append("")
        for w_name, w_info in workers.items():
            desc = w_info.get("description", "")
            entry = f"- **{w_name}**"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)
        lines.append("")

    # Brothers
    if brothers:
        lines.append("## Brothers")
        lines.append("")
        for bro_name, bro_info in brothers.items():
            desc = bro_info.get("description", "")
            role = bro_info.get("role", "worker")
            entry = f"- **{bro_name}** ({role})"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)
        lines.append("")

    lines.append(MARKER_END)
    return "\n".join(lines)


def generate_worker_identity(
    name: str,
    clade_name: str,
    personality: str = "",
    role: str = "worker",
    personal_name: str = "",
    brothers: dict[str, dict] | None = None,
) -> str:
    """Generate a CLAUDE.md identity section for a worker brother.

    Args:
        name: The worker brother's name.
        clade_name: Name of the clade.
        personality: Optional personality description.
        role: The brother's role.
        personal_name: Name of the personal coordinator.
        brothers: Dict of other brother names to info dicts.

    Returns:
        Markdown string wrapped in identity markers.
    """
    lines = [
        MARKER_START,
        f"# {clade_name} — Identity",
        "",
        f"**Name:** {name}",
        f"**Role:** {role}",
        "",
    ]

    if personality:
        lines.append(f"**Personality:** {personality}")
    else:
        lines.append("**Personality:** No personality description provided.")
    lines.append("")

    # MCP tools
    lines.append("## Available Tools (clade-worker)")
    lines.append("")
    lines.append("- `send_message` — Send a message via the Hearth")
    lines.append("- `check_mailbox` — Check for messages")
    lines.append("- `read_message` — Read a specific message")
    lines.append("- `browse_feed` — Browse all messages")
    lines.append("- `unread_count` — Get unread message count")
    lines.append("- `list_tasks` — List tasks from the Hearth")
    lines.append("- `get_task` — Get task details")
    lines.append("- `update_task` — Update task status")
    lines.append("- `deposit_morsel` — Deposit a note/observation (linkable to tasks, brothers, cards)")
    lines.append("- `list_morsels` — List morsels (filter by creator, tag, task_id, card_id)")
    lines.append("- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board (cards support links to tasks, morsels, trees, messages, other cards)")
    lines.append("")

    # Family list
    lines.append("## Family")
    lines.append("")
    if personal_name:
        lines.append(f"- **{personal_name}** (coordinator)")
    if brothers:
        for bro_name, bro_info in brothers.items():
            if bro_name == name:
                continue
            desc = bro_info.get("description", "")
            bro_role = bro_info.get("role", "worker")
            entry = f"- **{bro_name}** ({bro_role})"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)
    lines.append("")

    lines.append(MARKER_END)
    return "\n".join(lines)


def upsert_identity_section(existing_content: str, identity_section: str) -> str:
    """Insert or replace the identity section in CLAUDE.md content.

    Pure function — no I/O.

    Args:
        existing_content: Current file content (may be empty).
        identity_section: The identity section to insert (with markers).

    Returns:
        Updated content string.
    """
    if not existing_content:
        return identity_section + "\n"

    start_idx = existing_content.find(MARKER_START)
    end_idx = existing_content.find(MARKER_END)

    if start_idx != -1 and end_idx != -1:
        # Both markers found — replace between them (inclusive)
        end_idx += len(MARKER_END)
        return existing_content[:start_idx] + identity_section + existing_content[end_idx:]

    # No markers (or only start marker) — append
    return existing_content.rstrip("\n") + "\n\n" + identity_section + "\n"


def write_identity_local(
    identity_section: str,
    claude_md_path: Path | None = None,
) -> Path:
    """Write identity section to the local ~/.claude/CLAUDE.md.

    Args:
        identity_section: The identity section to write.
        claude_md_path: Override path (default: ~/.claude/CLAUDE.md).

    Returns:
        The path written to.
    """
    path = claude_md_path or (Path.home() / ".claude" / "CLAUDE.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if path.exists():
        existing = path.read_text()

    updated = upsert_identity_section(existing, identity_section)
    path.write_text(updated)
    return path


def write_identity_remote(
    ssh_host: str,
    identity_section: str,
    ssh_key: str | None = None,
) -> SSHResult:
    """Write identity section to a remote brother's ~/.claude/CLAUDE.md.

    Uses SSH + a Python script to perform the upsert on the remote host.

    Args:
        ssh_host: SSH host string (e.g. 'ian@masuda').
        identity_section: The identity section to write.
        ssh_key: Optional path to SSH private key.

    Returns:
        SSHResult from the remote operation.
    """
    encoded = base64.b64encode(identity_section.encode()).decode()

    script = f"""\
#!/bin/bash
set -e
python3 -c "
import base64, os
from pathlib import Path

MARKER_START = '<!-- CLADE_IDENTITY_START -->'
MARKER_END = '<!-- CLADE_IDENTITY_END -->'

identity = base64.b64decode('{encoded}').decode()

path = Path.home() / '.claude' / 'CLAUDE.md'
path.parent.mkdir(parents=True, exist_ok=True)

existing = ''
if path.exists():
    existing = path.read_text()

if not existing:
    updated = identity + chr(10)
else:
    start_idx = existing.find(MARKER_START)
    end_idx = existing.find(MARKER_END)
    if start_idx != -1 and end_idx != -1:
        end_idx += len(MARKER_END)
        updated = existing[:start_idx] + identity + existing[end_idx:]
    else:
        updated = existing.rstrip(chr(10)) + chr(10) + chr(10) + identity + chr(10)

path.write_text(updated)
print('IDENTITY_OK')
"
"""
    return run_remote(ssh_host, script, ssh_key=ssh_key, timeout=15)
