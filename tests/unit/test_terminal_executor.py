"""Unit tests for AppleScript execution via osascript."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from clade.terminal.executor import run_applescript


class TestRunApplescript:
    @patch("clade.terminal.executor.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert run_applescript("some script") == "OK"
        mock_run.assert_called_once_with(
            ["osascript", "-e", "some script"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("clade.terminal.executor.subprocess.run")
    def test_failure_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="execution error: blah"
        )
        result = run_applescript("bad script")
        assert result.startswith("Error:")
        assert "execution error: blah" in result

    @patch("clade.terminal.executor.subprocess.run")
    def test_timeout_propagates(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=10)
        with pytest.raises(subprocess.TimeoutExpired):
            run_applescript("slow script")

    @patch("clade.terminal.executor.subprocess.run")
    def test_passes_script_as_single_arg(self, mock_run):
        """The script should be passed as a single -e argument, not split."""
        mock_run.return_value = MagicMock(returncode=0)
        multiline_script = 'tell application "iTerm2"\n    activate\nend tell'
        run_applescript(multiline_script)
        args = mock_run.call_args[0][0]
        assert args == ["osascript", "-e", multiline_script]
