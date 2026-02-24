"""Template loading for Clade."""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent


def render_template(name: str) -> str:
    """Read a template file from the templates directory.

    Args:
        name: Template filename (e.g. 'hearth-bridge.yml').

    Returns:
        The template content as a string.

    Raises:
        FileNotFoundError: If the template doesn't exist.
    """
    path = TEMPLATES_DIR / name
    return path.read_text()
