"""Tests for terminal-spawner MCP server."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from brothers import BROTHERS
from terminal import generate_applescript, run_applescript
from server import spawn_terminal, connect_to_brother


# ---------------------------------------------------------------------------
# brothers.py — configuration sanity checks
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
# terminal.py — generate_applescript
# ---------------------------------------------------------------------------


class TestGenerateApplescriptIterm2:
    """Tests for iTerm2 AppleScript generation."""

    def test_no_command(self):
        script = generate_applescript(command=None, app="iterm2")
        assert 'tell application "iTerm2"' in script
        assert "activate" in script
        assert "create window with default profile" in script
        assert "write text" not in script

    def test_simple_command(self):
        script = generate_applescript(command="ls", app="iterm2")
        assert 'tell application "iTerm2"' in script
        assert "write text" in script
        assert "ls" in script

    def test_has_end_tell(self):
        script = generate_applescript(command="ls", app="iterm2")
        # With a command, we have a nested tell block, so need 2 end tells
        assert script.count("end tell") == 2

    def test_no_command_has_one_end_tell(self):
        script = generate_applescript(command=None, app="iterm2")
        assert script.count("end tell") == 1

    def test_command_with_double_quotes(self):
        """Commands containing double quotes must be properly escaped in
        the AppleScript string.  This is the known iTerm2 bug — the raw
        command gets interpolated into an AppleScript double-quoted string
        without escaping the inner quotes, producing invalid AppleScript.

        e.g.  write text "ssh -t cluster "claude""   ← broken
               write text "ssh -t cluster \"claude\""  ← correct
        """
        cmd = 'ssh -t cluster "claude"'
        script = generate_applescript(command=cmd, app="iterm2")

        # The write text line must wrap the FULL command in quotes.
        # Find the write text line and verify it is well-formed.
        lines = script.splitlines()
        write_line = [l for l in lines if "write text" in l][0].strip()

        # After `write text `, the rest should be one valid quoted string.
        # That means the inner double quotes must be escaped with backslash.
        # A naive check: the unescaped command quotes should NOT appear
        # literally between the outer AppleScript quotes.
        #
        # Valid:    write text "ssh -t cluster \"claude\""
        # Invalid:  write text "ssh -t cluster "claude""
        after_write_text = write_line[len("write text "):]

        # It should start and end with exactly one double-quote each
        assert after_write_text.startswith('"'), (
            f"write text value should start with a quote: {write_line}"
        )
        assert after_write_text.endswith('"'), (
            f"write text value should end with a quote: {write_line}"
        )

        # Strip the outer quotes and check the inner content
        inner = after_write_text[1:-1]

        # The inner content must NOT contain unescaped double-quotes,
        # because that would break the AppleScript string literal.
        # Walk through looking for unescaped quotes:
        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner):
                i += 2  # skip escaped char
                continue
            assert inner[i] != '"', (
                f"Unescaped double-quote found in AppleScript string at "
                f"position {i}: {write_line}"
            )
            i += 1

    def test_command_with_single_quotes(self):
        """Single quotes don't need escaping in AppleScript double-quoted
        strings, but let's make sure they pass through fine."""
        cmd = "echo 'hello world'"
        script = generate_applescript(command=cmd, app="iterm2")
        assert "echo 'hello world'" in script

    def test_brother_jerry_command(self):
        """Jerry's actual SSH command contains double quotes —
        this is the real-world trigger for the quoting bug."""
        cmd = BROTHERS["jerry"]["command"]
        script = generate_applescript(command=cmd, app="iterm2")

        # The generated script should be parseable by osascript.
        # At minimum, verify the quoting is correct.
        lines = script.splitlines()
        write_line = [l for l in lines if "write text" in l][0].strip()
        after_write_text = write_line[len("write text "):]
        inner = after_write_text[1:-1]

        # No unescaped quotes inside the string
        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner):
                i += 2
                continue
            assert inner[i] != '"', (
                f"Jerry's command produces broken AppleScript: {write_line}"
            )
            i += 1

    def test_brother_oppy_command(self):
        """Oppy's command also contains double quotes."""
        cmd = BROTHERS["oppy"]["command"]
        script = generate_applescript(command=cmd, app="iterm2")

        lines = script.splitlines()
        write_line = [l for l in lines if "write text" in l][0].strip()
        after_write_text = write_line[len("write text "):]
        inner = after_write_text[1:-1]

        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner):
                i += 2
                continue
            assert inner[i] != '"', (
                f"Oppy's command produces broken AppleScript: {write_line}"
            )
            i += 1

    def test_command_with_backslashes(self):
        """Backslashes in commands should also be escaped for AppleScript."""
        cmd = "echo foo\\bar"
        script = generate_applescript(command=cmd, app="iterm2")
        # Should not crash and should contain the command in some form
        assert "write text" in script

    def test_command_with_special_chars(self):
        """Commands with $, &, ;, pipes etc. should be passed through."""
        cmd = "cd /tmp && ls -la | grep foo"
        script = generate_applescript(command=cmd, app="iterm2")
        assert "write text" in script


class TestGenerateApplescriptTerminal:
    """Tests for Terminal.app AppleScript generation."""

    def test_no_command(self):
        script = generate_applescript(command=None, app="terminal")
        assert 'tell application "Terminal"' in script
        assert "activate" in script
        assert 'do script ""' in script

    def test_simple_command(self):
        script = generate_applescript(command="ls", app="terminal")
        assert 'tell application "Terminal"' in script
        assert 'do script "ls"' in script

    def test_has_one_end_tell(self):
        script = generate_applescript(command="ls", app="terminal")
        assert script.count("end tell") == 1

    def test_command_with_double_quotes(self):
        """Terminal.app has the same quoting concern as iTerm2."""
        cmd = 'ssh -t cluster "claude"'
        script = generate_applescript(command=cmd, app="terminal")

        lines = script.splitlines()
        do_script_line = [l for l in lines if "do script" in l][0].strip()
        after_do_script = do_script_line[len("do script "):]
        inner = after_do_script[1:-1]

        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner):
                i += 2
                continue
            assert inner[i] != '"', (
                f"Unescaped double-quote in Terminal.app script: {do_script_line}"
            )
            i += 1


class TestGenerateApplescriptUnknownApp:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown terminal app"):
            generate_applescript(command="ls", app="unknown")

    def test_raises_value_error_no_command(self):
        with pytest.raises(ValueError, match="Unknown terminal app"):
            generate_applescript(command=None, app="nope")


# ---------------------------------------------------------------------------
# terminal.py — run_applescript
# ---------------------------------------------------------------------------


class TestRunApplescript:
    @patch("terminal.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert run_applescript("some script") == "OK"
        mock_run.assert_called_once_with(
            ["osascript", "-e", "some script"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("terminal.subprocess.run")
    def test_failure_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="execution error: blah"
        )
        result = run_applescript("bad script")
        assert result.startswith("Error:")
        assert "execution error: blah" in result

    @patch("terminal.subprocess.run")
    def test_timeout_propagates(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=10)
        with pytest.raises(subprocess.TimeoutExpired):
            run_applescript("slow script")

    @patch("terminal.subprocess.run")
    def test_passes_script_as_single_arg(self, mock_run):
        """The script should be passed as a single -e argument, not split."""
        mock_run.return_value = MagicMock(returncode=0)
        multiline_script = 'tell application "iTerm2"\n    activate\nend tell'
        run_applescript(multiline_script)
        args = mock_run.call_args[0][0]
        assert args == ["osascript", "-e", multiline_script]


# ---------------------------------------------------------------------------
# server.py — spawn_terminal
# ---------------------------------------------------------------------------


class TestSpawnTerminal:
    @patch("server.run_applescript", return_value="OK")
    @patch("server.generate_applescript", return_value="mock script")
    def test_with_command_success(self, mock_gen, mock_run):
        result = spawn_terminal(command="ls", app="iterm2")
        assert "Opened new iterm2 window" in result
        assert "ls" in result
        mock_gen.assert_called_once_with("ls", "iterm2")
        mock_run.assert_called_once_with("mock script")

    @patch("server.run_applescript", return_value="OK")
    @patch("server.generate_applescript", return_value="mock script")
    def test_no_command_success(self, mock_gen, mock_run):
        result = spawn_terminal(command=None, app="iterm2")
        assert result == "Opened new iterm2 window"

    @patch("server.run_applescript", return_value="OK")
    @patch("server.generate_applescript", return_value="mock script")
    def test_terminal_app(self, mock_gen, mock_run):
        result = spawn_terminal(command="ls", app="terminal")
        assert "terminal" in result
        mock_gen.assert_called_once_with("ls", "terminal")

    @patch("server.run_applescript", return_value="Error: some failure")
    @patch("server.generate_applescript", return_value="mock script")
    def test_error_propagated(self, mock_gen, mock_run):
        result = spawn_terminal(command="ls", app="iterm2")
        assert result == "Error: some failure"


# ---------------------------------------------------------------------------
# server.py — connect_to_brother
# ---------------------------------------------------------------------------


class TestConnectToBrother:
    @patch("server.run_applescript", return_value="OK")
    @patch("server.generate_applescript", return_value="mock script")
    def test_jerry_success(self, mock_gen, mock_run):
        result = connect_to_brother(name="jerry")
        assert "Brother Jerry" in result
        mock_gen.assert_called_once_with(BROTHERS["jerry"]["command"], "terminal")

    @patch("server.run_applescript", return_value="OK")
    @patch("server.generate_applescript", return_value="mock script")
    def test_oppy_success(self, mock_gen, mock_run):
        result = connect_to_brother(name="oppy")
        assert "Brother Oppy" in result
        mock_gen.assert_called_once_with(BROTHERS["oppy"]["command"], "terminal")

    @patch("server.run_applescript", return_value="Error: could not connect")
    @patch("server.generate_applescript", return_value="mock script")
    def test_error_propagated(self, mock_gen, mock_run):
        result = connect_to_brother(name="jerry")
        assert result == "Error: could not connect"

    def test_unknown_brother(self):
        result = connect_to_brother(name="unknown")
        assert "Unknown brother" in result
        assert "jerry" in result
        assert "oppy" in result

    @patch("server.run_applescript", return_value="OK")
    @patch("server.generate_applescript", return_value="mock script")
    def test_always_uses_terminal(self, mock_gen, mock_run):
        """Brother connections should always use Terminal.app."""
        connect_to_brother(name="jerry")
        args = mock_gen.call_args[0]
        assert args[1] == "terminal"


# ---------------------------------------------------------------------------
# Integration-style tests (still mocking osascript, but testing the full
# generate → run pipeline)
# ---------------------------------------------------------------------------


class TestIntegration:
    @patch("terminal.subprocess.run")
    def test_spawn_iterm2_with_command_end_to_end(self, mock_run):
        """Full path: spawn_terminal → generate_applescript → run_applescript."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = spawn_terminal(command="htop", app="iterm2")
        assert "Opened new iterm2 window" in result

        # Verify osascript was called with a valid-looking script
        script = mock_run.call_args[0][0][2]  # ["osascript", "-e", script]
        assert 'tell application "iTerm2"' in script
        assert "htop" in script

    @patch("terminal.subprocess.run")
    def test_connect_to_jerry_end_to_end(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = connect_to_brother(name="jerry")
        assert "Brother Jerry" in result

        script = mock_run.call_args[0][0][2]
        assert 'tell application "Terminal"' in script
        assert "ssh" in script
        assert "cluster" in script

    @patch("terminal.subprocess.run")
    def test_connect_to_oppy_end_to_end(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = connect_to_brother(name="oppy")
        assert "Brother Oppy" in result

        script = mock_run.call_args[0][0][2]
        assert 'tell application "Terminal"' in script
        assert "ssh" in script
        assert "masuda" in script
