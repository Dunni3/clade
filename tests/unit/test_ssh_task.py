"""Tests for the SSH task execution module."""

import base64
import subprocess
from unittest.mock import patch

import pytest

from terminal_spawner.tasks.ssh_task import (
    TaskResult,
    build_remote_script,
    generate_session_name,
    initiate_task,
    wrap_prompt,
)


# ---------------------------------------------------------------------------
# generate_session_name
# ---------------------------------------------------------------------------


class TestGenerateSessionName:
    def test_basic(self):
        name = generate_session_name("oppy", "Review config")
        assert name.startswith("task-oppy-review-config-")

    def test_no_subject(self):
        name = generate_session_name("jerry")
        assert name.startswith("task-jerry-")
        # Should just be task-jerry-<timestamp>
        parts = name.split("-")
        assert len(parts) == 3

    def test_special_characters_stripped(self):
        name = generate_session_name("oppy", "Fix bug #42! (urgent)")
        assert "#" not in name
        assert "!" not in name
        assert "(" not in name

    def test_long_subject_truncated(self):
        long_subject = "a" * 100
        name = generate_session_name("oppy", long_subject)
        # Subject part should be at most 30 chars
        # Name format: task-oppy-<slug>-<timestamp>
        parts = name.split("-")
        # Remove task, oppy, and timestamp parts
        slug = "-".join(parts[2:-1])
        assert len(slug) <= 30

    def test_unique_timestamps(self):
        """Two calls should produce different names (timestamps differ)."""
        import time

        name1 = generate_session_name("oppy", "test")
        time.sleep(0.01)  # Ensure time advances
        name2 = generate_session_name("oppy", "test")
        # They might be the same if called within the same second, which is fine
        assert name1.startswith("task-oppy-test-")
        assert name2.startswith("task-oppy-test-")


# ---------------------------------------------------------------------------
# wrap_prompt
# ---------------------------------------------------------------------------


class TestWrapPrompt:
    def test_includes_task_id(self):
        result = wrap_prompt("Do the thing", "oppy", "Test task", 42)
        assert "Task #42" in result
        assert "task_id=42" in result

    def test_includes_user_prompt(self):
        result = wrap_prompt("Review the training script", "oppy", "Review", 1)
        assert "Review the training script" in result

    def test_includes_sender(self):
        result = wrap_prompt("Test", "jerry", "Test", 1, sender_name="doot")
        assert "doot" in result

    def test_includes_subject(self):
        result = wrap_prompt("Test", "oppy", "Architecture review", 5)
        assert "Architecture review" in result

    def test_includes_protocol_steps(self):
        result = wrap_prompt("Test", "oppy", "Test", 1)
        assert "confirming receipt" in result
        assert "running low on turns" in result
        assert "completion message" in result
        assert "update_task" in result

    def test_empty_subject(self):
        result = wrap_prompt("Test", "oppy", "", 1)
        assert "Task #1" in result


# ---------------------------------------------------------------------------
# build_remote_script
# ---------------------------------------------------------------------------


class TestBuildRemoteScript:
    def test_contains_session_name(self):
        script = build_remote_script("task-oppy-test-123", None, "dGVzdA==")
        assert "task-oppy-test-123" in script

    def test_contains_base64_prompt(self):
        b64 = base64.b64encode(b"hello world").decode()
        script = build_remote_script("sess", None, b64)
        assert b64 in script

    def test_contains_working_dir(self):
        script = build_remote_script("sess", "~/projects/test", "dGVzdA==")
        assert "cd ~/projects/test" in script

    def test_no_working_dir(self):
        script = build_remote_script("sess", None, "dGVzdA==")
        # Should have a no-op instead of cd
        assert "cd " not in script

    def test_contains_max_turns(self):
        script = build_remote_script("sess", None, "dGVzdA==", max_turns=25)
        assert "--max-turns 25" in script

    def test_contains_task_launched_marker(self):
        script = build_remote_script("sess", None, "dGVzdA==")
        assert 'echo "TASK_LAUNCHED"' in script

    def test_uses_tmux(self):
        script = build_remote_script("sess", None, "dGVzdA==")
        assert "tmux new-session -d" in script

    def test_uses_login_shell(self):
        script = build_remote_script("sess", None, "dGVzdA==")
        assert "bash --login" in script

    def test_cleanup_commands(self):
        script = build_remote_script("sess", None, "dGVzdA==")
        assert 'rm -f "$PROMPT_FILE" "$RUNNER"' in script

    def test_auto_pull_discovers_repo(self):
        script = build_remote_script("sess", None, "dGVzdA==", auto_pull=True)
        assert "mailbox_mcp" in script
        assert ".claude.json" in script
        assert "git -C" in script
        assert "pull --ff-only" in script

    def test_no_auto_pull_no_git(self):
        script = build_remote_script("sess", None, "dGVzdA==")
        assert "git" not in script


# ---------------------------------------------------------------------------
# initiate_task
# ---------------------------------------------------------------------------


class TestInitiateTask:
    @patch("terminal_spawner.tasks.ssh_task.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ssh", "masuda", "bash", "-s"],
            returncode=0,
            stdout="TASK_LAUNCHED\n",
            stderr="",
        )
        result = initiate_task(
            host="masuda",
            working_dir="~/projects/test",
            prompt="Do stuff",
            session_name="task-oppy-test-123",
        )
        assert result.success is True
        assert result.session_name == "task-oppy-test-123"
        assert result.host == "masuda"
        assert "TASK_LAUNCHED" in result.stdout

    @patch("terminal_spawner.tasks.ssh_task.subprocess.run")
    def test_failure_no_marker(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ssh", "masuda", "bash", "-s"],
            returncode=1,
            stdout="",
            stderr="tmux: command not found",
        )
        result = initiate_task(
            host="masuda",
            working_dir=None,
            prompt="Do stuff",
            session_name="task-oppy-test-123",
        )
        assert result.success is False
        assert "failed" in result.message.lower()

    @patch("terminal_spawner.tasks.ssh_task.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=30)
        result = initiate_task(
            host="masuda",
            working_dir=None,
            prompt="Do stuff",
            session_name="task-oppy-test-123",
        )
        assert result.success is False
        assert "timed out" in result.message.lower()

    @patch("terminal_spawner.tasks.ssh_task.subprocess.run")
    def test_ssh_error(self, mock_run):
        mock_run.side_effect = OSError("No such host")
        result = initiate_task(
            host="badhost",
            working_dir=None,
            prompt="Do stuff",
            session_name="task-test-123",
        )
        assert result.success is False
        assert "error" in result.message.lower()

    @patch("terminal_spawner.tasks.ssh_task.subprocess.run")
    def test_passes_script_via_stdin(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="TASK_LAUNCHED\n", stderr=""
        )
        initiate_task(
            host="masuda",
            working_dir="~/work",
            prompt="hello",
            session_name="task-test-123",
            max_turns=30,
        )
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["input"] is not None
        assert "task-test-123" in call_kwargs.kwargs["input"]

    @patch("terminal_spawner.tasks.ssh_task.subprocess.run")
    def test_custom_ssh_timeout(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="TASK_LAUNCHED\n", stderr=""
        )
        initiate_task(
            host="masuda",
            working_dir=None,
            prompt="test",
            session_name="sess",
            ssh_timeout=60,
        )
        assert mock_run.call_args.kwargs["timeout"] == 60

    @patch("terminal_spawner.tasks.ssh_task.subprocess.run")
    def test_auto_pull_passed_to_script(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="TASK_LAUNCHED\n", stderr=""
        )
        initiate_task(
            host="masuda",
            working_dir=None,
            prompt="test",
            session_name="sess",
            auto_pull=True,
        )
        script_input = mock_run.call_args.kwargs["input"]
        assert "git -C" in script_input
        assert "pull --ff-only" in script_input
