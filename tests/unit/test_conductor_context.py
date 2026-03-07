"""Unit tests for conductor context assembly."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clade.conductor.context import (
    build_user_message,
    detect_tick_type,
    load_system_prompt,
    render_tick_prompt,
)


class TestDetectTickType:
    def test_periodic(self, monkeypatch):
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        assert detect_tick_type() == "periodic"

    def test_event(self, monkeypatch):
        monkeypatch.setenv("TRIGGER_TASK_ID", "42")
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        assert detect_tick_type() == "event"

    def test_message(self, monkeypatch):
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.setenv("TRIGGER_MESSAGE_ID", "7")
        assert detect_tick_type() == "message"

    def test_task_id_takes_priority(self, monkeypatch):
        """TRIGGER_TASK_ID takes priority over TRIGGER_MESSAGE_ID."""
        monkeypatch.setenv("TRIGGER_TASK_ID", "1")
        monkeypatch.setenv("TRIGGER_MESSAGE_ID", "2")
        assert detect_tick_type() == "event"


class TestRenderTickPrompt:
    def test_renders_from_repo_templates(self):
        """render_tick_prompt should find and render from deploy/conductor-tick/."""
        result = render_tick_prompt("periodic")
        assert "Kamaji" in result
        assert "Periodic" in result

    def test_each_type_has_distinct_content(self):
        periodic = render_tick_prompt("periodic")
        event = render_tick_prompt("event")
        message = render_tick_prompt("message")
        # Each type must be different
        assert periodic != event
        assert periodic != message
        assert event != message

    def test_event_template_mentions_trigger_task(self):
        result = render_tick_prompt("event")
        assert "TRIGGER_TASK_ID" in result

    def test_message_template_mentions_trigger_message(self):
        result = render_tick_prompt("message")
        assert "TRIGGER_MESSAGE_ID" in result

    def test_periodic_template_mentions_stuck_tasks(self):
        result = render_tick_prompt("periodic")
        assert "stuck" in result.lower() or "launched" in result

    def test_common_rules_included_in_all_types(self):
        for tick_type in ("periodic", "event", "message"):
            result = render_tick_prompt(tick_type)
            assert "Killed tasks" in result
            assert "Retry limits" in result

    def test_explicit_template_dir(self, tmp_path):
        """Explicit template_dir overrides default search."""
        # Create minimal templates in tmp_path
        common = tmp_path / "_common.md.j2"
        common.write_text("# Common\n")
        (tmp_path / "tick_periodic.md.j2").write_text("{% include '_common.md.j2' %}Periodic only\n")
        result = render_tick_prompt("periodic", template_dir=tmp_path)
        assert "Common" in result
        assert "Periodic only" in result

    def test_file_not_found_raises(self, tmp_path):
        """FileNotFoundError raised when no templates exist."""
        import clade.conductor.context as ctx_module
        import unittest.mock as mock
        with mock.patch.object(ctx_module, "DEFAULT_TICK_TEMPLATE_DIR", tmp_path / "nonexistent"):
            with mock.patch.object(ctx_module, "_REPO_TICK_TEMPLATE_DIR", tmp_path / "nonexistent2"):
                with pytest.raises(FileNotFoundError):
                    render_tick_prompt("periodic")


class TestLoadSystemPrompt:
    def test_explicit_path(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test Prompt")
        result = load_system_prompt(prompt_file)
        assert result == "# Test Prompt"

    def test_env_override(self, tmp_path, monkeypatch):
        prompt_file = tmp_path / "env-prompt.md"
        prompt_file.write_text("# Env Prompt")
        monkeypatch.setenv("CONDUCTOR_TICK_PROMPT", str(prompt_file))
        result = load_system_prompt()
        assert result == "# Env Prompt"

    def test_template_based_fallback(self, monkeypatch):
        """When no explicit path or env var, templates are used."""
        monkeypatch.delenv("CONDUCTOR_TICK_PROMPT", raising=False)
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        result = load_system_prompt()
        assert "Kamaji" in result
        assert "Periodic" in result

    def test_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONDUCTOR_TICK_PROMPT", raising=False)
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        import clade.conductor.context as ctx_module
        import unittest.mock as mock
        # Patch all paths so nothing is found
        monkeypatch.setattr(ctx_module, "DEFAULT_TICK_PROMPT_PATH", tmp_path / "nope1.md")
        monkeypatch.setattr(ctx_module, "_REPO_TICK_PROMPT", tmp_path / "nope2.md")
        with mock.patch.object(ctx_module, "DEFAULT_TICK_TEMPLATE_DIR", tmp_path / "nope3"):
            with mock.patch.object(ctx_module, "_REPO_TICK_TEMPLATE_DIR", tmp_path / "nope4"):
                with pytest.raises(FileNotFoundError):
                    load_system_prompt(tmp_path / "nonexistent.md")

    def test_repo_fallback(self, monkeypatch):
        """The deploy/conductor-tick templates should exist in the repo."""
        monkeypatch.delenv("CONDUCTOR_TICK_PROMPT", raising=False)
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        repo_root = Path(__file__).resolve().parent.parent.parent
        tick_dir = repo_root / "deploy" / "conductor-tick"
        if tick_dir.exists():
            result = load_system_prompt()
            assert "Kamaji" in result

    def test_legacy_monolithic_fallback(self, tmp_path, monkeypatch):
        """Falls back to monolithic conductor-tick.md if templates missing."""
        monkeypatch.delenv("CONDUCTOR_TICK_PROMPT", raising=False)
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        import clade.conductor.context as ctx_module
        import unittest.mock as mock

        monolithic = tmp_path / "conductor-tick.md"
        monolithic.write_text("# Monolithic Prompt")

        monkeypatch.setattr(ctx_module, "DEFAULT_TICK_PROMPT_PATH", monolithic)
        with mock.patch.object(ctx_module, "DEFAULT_TICK_TEMPLATE_DIR", tmp_path / "no-templates"):
            with mock.patch.object(ctx_module, "_REPO_TICK_TEMPLATE_DIR", tmp_path / "no-templates2"):
                result = load_system_prompt()
        assert result == "# Monolithic Prompt"


class TestBuildUserMessage:
    def test_periodic_tick(self, monkeypatch):
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        msg = build_user_message()
        assert "Periodic" in msg
        assert "Current time" in msg

    def test_event_driven_tick(self, monkeypatch):
        monkeypatch.setenv("TRIGGER_TASK_ID", "42")
        monkeypatch.delenv("TRIGGER_MESSAGE_ID", raising=False)
        msg = build_user_message()
        assert "Event-driven" in msg
        assert "task #42" in msg
        assert "TRIGGER_TASK_ID=42" in msg

    def test_message_driven_tick(self, monkeypatch):
        monkeypatch.delenv("TRIGGER_TASK_ID", raising=False)
        monkeypatch.setenv("TRIGGER_MESSAGE_ID", "7")
        msg = build_user_message()
        assert "Message-driven" in msg
        assert "message #7" in msg
        assert "TRIGGER_MESSAGE_ID=7" in msg
