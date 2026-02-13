"""Integration tests for the MCP server tools."""

import subprocess
from unittest.mock import MagicMock, patch

from clade.core.config import FALLBACK_CONFIG
from clade.terminal.applescript import generate_applescript
from clade.terminal.executor import run_applescript

# For testing, we'll use the fallback config brothers
BROTHERS = FALLBACK_CONFIG["brothers"]


# ---------------------------------------------------------------------------
# Brothers configuration sanity checks
# ---------------------------------------------------------------------------


class TestBrothersConfig:
    def test_jerry_exists(self):
        assert "jerry" in BROTHERS

    def test_oppy_exists(self):
        assert "oppy" in BROTHERS

    def test_jerry_has_required_keys(self):
        for key in ("host", "working_dir", "command", "description"):
            assert key in BROTHERS["jerry"]

    def test_oppy_has_required_keys(self):
        for key in ("host", "working_dir", "command", "description"):
            assert key in BROTHERS["oppy"]

    def test_jerry_command_uses_ssh(self):
        assert BROTHERS["jerry"]["command"].startswith("ssh")

    def test_oppy_command_uses_ssh(self):
        assert BROTHERS["oppy"]["command"].startswith("ssh")


# ---------------------------------------------------------------------------
# Terminal spawning integration tests (using tool logic directly)
# ---------------------------------------------------------------------------


class TestTerminalSpawningIntegration:
    """Test terminal spawning logic end-to-end."""

    @patch("clade.terminal.executor.subprocess.run")
    def test_spawn_with_command_success(self, mock_run):
        """Test spawning terminal with command via generate + run pipeline."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        script = generate_applescript("ls", "iterm2")
        result = run_applescript(script)

        assert result == "OK"
        assert 'tell application "iTerm2"' in script
        assert "ls" in script

    @patch("clade.terminal.executor.subprocess.run")
    def test_spawn_terminal_app(self, mock_run):
        """Test spawning with Terminal.app."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        script = generate_applescript("htop", "terminal")
        result = run_applescript(script)

        assert result == "OK"
        assert 'tell application "Terminal"' in script
        assert "htop" in script


class TestBrotherConnectionIntegration:
    """Test brother connection logic end-to-end."""

    @patch("clade.terminal.executor.subprocess.run")
    def test_connect_to_jerry(self, mock_run):
        """Test connecting to Jerry with full pipeline."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        jerry_command = BROTHERS["jerry"]["command"]
        script = generate_applescript(jerry_command, "terminal")
        result = run_applescript(script)

        assert result == "OK"
        assert 'tell application "Terminal"' in script
        assert "ssh" in script
        assert "cluster" in script

    @patch("clade.terminal.executor.subprocess.run")
    def test_connect_to_oppy(self, mock_run):
        """Test connecting to Oppy with full pipeline."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        oppy_command = BROTHERS["oppy"]["command"]
        script = generate_applescript(oppy_command, "terminal")
        result = run_applescript(script)

        assert result == "OK"
        assert 'tell application "Terminal"' in script
        assert "ssh" in script
        assert "masuda" in script

