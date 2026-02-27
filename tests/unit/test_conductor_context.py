"""Unit tests for conductor context assembly."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clade.conductor.context import build_user_message, load_system_prompt


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

    def test_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONDUCTOR_TICK_PROMPT", raising=False)
        # Patch out all fallback paths so nothing is found
        import clade.conductor.context as ctx_module
        monkeypatch.setattr(ctx_module, "DEFAULT_TICK_PROMPT_PATH", tmp_path / "nope1.md")
        monkeypatch.setattr(ctx_module, "_REPO_TICK_PROMPT", tmp_path / "nope2.md")
        with pytest.raises(FileNotFoundError):
            load_system_prompt(tmp_path / "nonexistent.md")

    def test_repo_fallback(self):
        """The deploy/conductor-tick.md should exist in the repo."""
        # This test verifies the fallback path works with the actual repo file
        repo_root = Path(__file__).resolve().parent.parent.parent
        tick_file = repo_root / "deploy" / "conductor-tick.md"
        if tick_file.exists():
            result = load_system_prompt()
            assert "Kamaji" in result


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
