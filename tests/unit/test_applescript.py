"""Unit tests for AppleScript generation."""

import pytest

from terminal_spawner.terminal.applescript import generate_applescript

# Hardcoded brother config for testing (matches current configuration)
BROTHERS = {
    "jerry": {
        "host": "cluster",
        "working_dir": None,
        "command": "ssh -t cluster \"bash -lc claude\"",
        "description": "Brother Jerry — GPU jobs on the cluster",
    },
    "oppy": {
        "host": "masuda",
        "working_dir": "~/projects/mol_diffusion/OMTRA_oppy",
        "command": "ssh -t masuda \"bash -lc 'cd ~/projects/mol_diffusion/OMTRA_oppy && claude'\"",
        "description": "Brother Oppy — The architect on masuda",
    },
}


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
