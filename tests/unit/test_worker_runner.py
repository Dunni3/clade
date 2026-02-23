"""Tests for the local tmux task runner."""

import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from clade.worker.runner import (
    LocalTaskResult,
    build_runner_script,
    launch_local_task,
    check_tmux_session,
    list_tmux_sessions,
)


class TestBuildRunnerScript:
    def test_creates_temp_files(self):
        prompt_path, runner_path = build_runner_script(
            "task-oppy-test-123", None, "Do the thing"
        )
        try:
            assert os.path.exists(prompt_path)
            assert os.path.exists(runner_path)
            # Prompt file has the prompt
            with open(prompt_path) as f:
                assert f.read() == "Do the thing"
            # Runner script is executable
            assert os.access(runner_path, os.X_OK)
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_runner_contains_claude_command(self):
        prompt_path, runner_path = build_runner_script(
            "task-oppy-test-123", None, "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "claude -p" in content
            assert "--dangerously-skip-permissions" in content
            assert prompt_path in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_working_dir(self):
        prompt_path, runner_path = build_runner_script(
            "sess", "~/projects/test", "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "cd ~/projects/test" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_no_working_dir(self):
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "cd " not in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_max_turns(self):
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello", max_turns=25
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "--max-turns 25" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_no_max_turns_by_default(self):
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "--max-turns" not in content
            assert "--dangerously-skip-permissions" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_env_vars_with_task_id(self):
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
            hearth_name="oppy",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "export CLAUDE_TASK_ID=42" in content
            assert "export HEARTH_URL='https://example.com'" in content
            assert "export HEARTH_API_KEY='secret'" in content
            assert "export HEARTH_NAME='oppy'" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_no_env_vars_without_task_id(self):
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "CLAUDE_TASK_ID" not in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_env_vars_without_hearth_url(self):
        """Ember delegation: task_id + api_key set, but no hearth_url override."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello",
            task_id=7,
            hearth_url=None,
            hearth_api_key="worker-key",
            hearth_name="testember",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            # Task ID and API key are exported
            assert "export CLAUDE_TASK_ID=7" in content
            assert "export HEARTH_API_KEY='worker-key'" in content
            assert "export HEARTH_NAME='testember'" in content
            # HEARTH_URL is NOT exported — worker's own env var is used
            assert "export HEARTH_URL" not in content
            assert "MAILBOX_URL" not in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_exit_handler_with_task_env(self):
        """Exit handler curl appears when task env vars are set."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
            hearth_name="oppy",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "Auto-report failure" in content
            assert "curl -skf -X PATCH" in content
            assert "CLAUDE_TASK_ID" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_no_exit_handler_without_task_env(self):
        """No exit handler when task env vars aren't set."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "Auto-report failure" not in content
            assert "curl" not in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_failure_trap_before_cd(self):
        """Trap is set before cd so pre-Claude failures are caught."""
        prompt_path, runner_path = build_runner_script(
            "sess", "~/projects/test", "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            trap_pos = content.index("trap '_report_failure $?' EXIT")
            cd_pos = content.index("cd ~/projects/test")
            assert trap_pos < cd_pos, "trap must be set before cd"
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_failure_trap_contains_report_function(self):
        """Trap includes _report_failure function with diagnostic info."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "_report_failure()" in content
            assert "_CLAUDE_STARTED=0" in content
            assert "before Claude started" in content
            assert "Session exited with code" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_claude_started_flag_before_claude(self):
        """_CLAUDE_STARTED=1 is set just before the claude command."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            started_pos = content.index("_CLAUDE_STARTED=1")
            claude_pos = content.index("claude -p")
            assert started_pos < claude_pos, "_CLAUDE_STARTED=1 must be before claude command"
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_no_trap_without_task_id(self):
        """No trap or _report_failure when task_id is not set."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "_report_failure" not in content
            assert "_CLAUDE_STARTED" not in content
            assert "trap " not in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_trap_not_fire_on_success(self):
        """Trap function checks exit code != 0, so it won't report on success."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            # The function checks for non-zero exit code
            assert '"$rc" -ne 0' in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_combined_trap_with_worktree(self):
        """When worktree isolation is active, trap combines cleanup + failure report."""
        prompt_path, runner_path = build_runner_script(
            "sess", "~/projects/test", "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "_cleanup_worktree; _report_failure" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_exit_with_exit_code(self):
        """Script ends with exit $EXIT_CODE to propagate correct code to trap."""
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello",
            task_id=42,
            hearth_url="https://example.com",
            hearth_api_key="secret",
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "exit $EXIT_CODE" in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)

    def test_self_cleanup(self):
        prompt_path, runner_path = build_runner_script(
            "sess", None, "hello"
        )
        try:
            with open(runner_path) as f:
                content = f.read()
            assert "rm -f" in content
            assert prompt_path in content
        finally:
            os.unlink(prompt_path)
            os.unlink(runner_path)


class TestLaunchLocalTask:
    @patch("clade.worker.runner.subprocess.run")
    @patch("clade.worker.runner.build_runner_script")
    def test_success(self, mock_build, mock_run):
        mock_build.return_value = ("/tmp/prompt.txt", "/tmp/runner.sh")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        result = launch_local_task("task-oppy-test-123", None, "do stuff")
        assert result.success is True
        assert result.session_name == "task-oppy-test-123"

    @patch("clade.worker.runner.subprocess.run")
    @patch("clade.worker.runner.build_runner_script")
    def test_tmux_failure(self, mock_build, mock_run):
        mock_build.return_value = ("/tmp/prompt.txt", "/tmp/runner.sh")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="duplicate session"
        )
        # Mock os.unlink to not fail on non-existent files
        with patch("clade.worker.runner.os.unlink"):
            result = launch_local_task("task-oppy-test-123", None, "do stuff")
        assert result.success is False
        assert "code 1" in result.message

    @patch("clade.worker.runner.subprocess.run")
    @patch("clade.worker.runner.build_runner_script")
    def test_exception_cleanup(self, mock_build, mock_run):
        mock_build.return_value = ("/tmp/prompt.txt", "/tmp/runner.sh")
        mock_run.side_effect = OSError("tmux not found")
        with patch("clade.worker.runner.os.unlink") as mock_unlink:
            result = launch_local_task("task-test", None, "do stuff")
        assert result.success is False
        assert "tmux" in result.message.lower()
        # Should try to clean up both files
        assert mock_unlink.call_count == 2


class TestCheckTmuxSession:
    @patch("clade.worker.runner.subprocess.run")
    def test_exists(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        assert check_tmux_session("task-oppy-123") is True

    @patch("clade.worker.runner.subprocess.run")
    def test_not_exists(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="no session"
        )
        assert check_tmux_session("task-oppy-123") is False

    @patch("clade.worker.runner.subprocess.run")
    def test_exception(self, mock_run):
        mock_run.side_effect = OSError("tmux not found")
        assert check_tmux_session("task-oppy-123") is False


class TestListTmuxSessions:
    @patch("clade.worker.runner.subprocess.run")
    def test_returns_matching_sessions(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="task-oppy-review-123\ntask-jerry-fix-456\nother-session\n",
            stderr=""
        )
        result = list_tmux_sessions(prefix="task-")
        assert result == ["task-oppy-review-123", "task-jerry-fix-456"]

    @patch("clade.worker.runner.subprocess.run")
    def test_no_sessions(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="no server running"
        )
        assert list_tmux_sessions() == []

    @patch("clade.worker.runner.subprocess.run")
    def test_exception(self, mock_run):
        mock_run.side_effect = OSError("tmux not found")
        assert list_tmux_sessions() == []
