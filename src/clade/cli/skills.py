"""Skill installation helper — copies bundled skills to ~/.claude/skills/."""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path


def get_bundled_skills() -> list[str]:
    """Return names of all bundled skills (subdirectories of clade/skills/ containing SKILL.md)."""
    skills_pkg = importlib.resources.files("clade") / "skills"
    names = []
    for item in skills_pkg.iterdir():
        if item.is_dir() and (item / "SKILL.md").is_file():
            names.append(item.name)
    return sorted(names)


def install_all_skills(target_dir: Path | None = None) -> dict[str, bool]:
    """Install all bundled skills to target_dir (default: ~/.claude/skills/).

    Returns a dict of {skill_name: success}.
    """
    if target_dir is None:
        target_dir = Path.home() / ".claude" / "skills"

    skills_pkg = importlib.resources.files("clade") / "skills"
    results: dict[str, bool] = {}

    for skill_name in get_bundled_skills():
        try:
            src = skills_pkg / skill_name
            dest = target_dir / skill_name
            dest.mkdir(parents=True, exist_ok=True)

            # Copy SKILL.md (and any other non-Python files)
            for item in src.iterdir():
                if item.name.startswith("__") or item.name.endswith(".pyc"):
                    continue
                dest_file = dest / item.name
                if item.is_file():
                    dest_file.write_text(item.read_text())
                elif item.is_dir() and not item.name.startswith("__"):
                    # Copy subdirectories (e.g. examples/, scripts/)
                    if dest_file.exists():
                        shutil.rmtree(dest_file)
                    shutil.copytree(str(item), str(dest_file))

            results[skill_name] = True
        except Exception:
            results[skill_name] = False

    return results
