"""Jinja2 template loader for bash script generation."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import jinja2


@lru_cache(maxsize=1)
def get_jinja_env() -> jinja2.Environment:
    """Return a cached Jinja2 environment loading from this directory."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(Path(__file__).parent),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )


def render_template(name: str, **kwargs: object) -> str:
    """Render a template by name with the given context."""
    return get_jinja_env().get_template(name).render(**kwargs)


def heredoc_escape(content: str, preserve_vars: list[str] | None = None) -> str:
    r"""Escape ``$`` for embedding inside an unquoted heredoc.

    All ``$`` are escaped to ``\$``, then any variables listed in
    *preserve_vars* are un-escaped so they expand at write time.
    """
    escaped = content.replace("$", "\\$")
    for var in preserve_vars or []:
        # Un-escape both $VAR and ${VAR} forms
        escaped = escaped.replace(f"\\${var}", f"${var}")
        escaped = escaped.replace(f"\\${{{var}}}", f"${{{var}}}")
    return escaped
