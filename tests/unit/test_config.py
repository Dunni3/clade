"""Unit tests for configuration loading."""

import tempfile
from pathlib import Path

import pytest

from terminal_spawner.core.config import (
    FALLBACK_CONFIG,
    get_brother_command,
    load_config,
)


class TestGetBrotherCommand:
    def test_brother_without_working_dir(self):
        brother = {
            "host": "cluster",
            "working_dir": None,
            "command": "",
            "description": "Test",
        }
        cmd = get_brother_command(brother)
        assert cmd == 'ssh -t cluster "bash -lc claude"'

    def test_brother_with_working_dir(self):
        brother = {
            "host": "masuda",
            "working_dir": "~/projects/foo",
            "command": "",
            "description": "Test",
        }
        cmd = get_brother_command(brother)
        assert cmd == 'ssh -t masuda "bash -lc \'cd ~/projects/foo && claude\'"'


class TestLoadConfig:
    def test_fallback_config_when_no_file(self):
        """When no config file exists, should return fallback config."""
        config = load_config(path=Path("/nonexistent/config.yaml"))
        assert config == FALLBACK_CONFIG
        assert "jerry" in config["brothers"]
        assert "oppy" in config["brothers"]

    def test_load_valid_yaml_config(self):
        """Should load configuration from valid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
default_terminal_app: iterm2
brothers:
  test-brother:
    host: test.example.com
    working_dir: ~/test
    description: "Test Brother"
mailbox:
  url: "https://example.com"
  name: "test"
""")
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_config(path=config_path)
            assert config["default_terminal_app"] == "iterm2"
            assert "test-brother" in config["brothers"]
            assert config["brothers"]["test-brother"]["host"] == "test.example.com"
            assert config["mailbox"]["url"] == "https://example.com"
        finally:
            config_path.unlink()

    def test_auto_generate_commands(self):
        """Should auto-generate SSH commands if not provided."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
brothers:
  auto-gen:
    host: auto.example.com
    working_dir: null
    description: "Auto-generated command"
""")
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_config(path=config_path)
            cmd = config["brothers"]["auto-gen"]["command"]
            assert cmd == 'ssh -t auto.example.com "bash -lc claude"'
        finally:
            config_path.unlink()

    def test_fallback_on_invalid_yaml(self):
        """Should fall back to default config if YAML is invalid."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()
            config_path = Path(f.name)

        try:
            with pytest.warns(UserWarning, match="Failed to load config"):
                config = load_config(path=config_path)
            assert config == FALLBACK_CONFIG
        finally:
            config_path.unlink()


class TestFallbackConfig:
    def test_jerry_exists(self):
        assert "jerry" in FALLBACK_CONFIG["brothers"]

    def test_oppy_exists(self):
        assert "oppy" in FALLBACK_CONFIG["brothers"]

    def test_default_terminal_app(self):
        assert FALLBACK_CONFIG["default_terminal_app"] == "terminal"

    def test_jerry_has_command(self):
        assert "command" in FALLBACK_CONFIG["brothers"]["jerry"]
        assert FALLBACK_CONFIG["brothers"]["jerry"]["command"].startswith("ssh")

    def test_oppy_has_command(self):
        assert "command" in FALLBACK_CONFIG["brothers"]["oppy"]
        assert FALLBACK_CONFIG["brothers"]["oppy"]["command"].startswith("ssh")
