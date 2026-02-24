"""Tests for skill installation."""

from pathlib import Path

from clade.cli.skills import get_bundled_skills, install_all_skills


def test_get_bundled_skills():
    """implement-card should be in the bundled skills list."""
    skills = get_bundled_skills()
    assert "implement-card" in skills


def test_install_skill(tmp_path: Path):
    """Skills install to the target directory with expected content."""
    results = install_all_skills(target_dir=tmp_path)
    assert results.get("implement-card") is True

    skill_md = tmp_path / "implement-card" / "SKILL.md"
    assert skill_md.exists()

    content = skill_md.read_text()
    assert "name: implement-card" in content
    assert "get_card" in content
    assert "initiate_ember_task" in content


def test_install_idempotent(tmp_path: Path):
    """Double install should succeed without error."""
    results1 = install_all_skills(target_dir=tmp_path)
    results2 = install_all_skills(target_dir=tmp_path)
    assert results1 == results2
    assert all(v is True for v in results2.values())
