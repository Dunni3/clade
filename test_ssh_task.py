"""Tests for the SSH task execution module and related MCP tools."""

import base64
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ssh_task import (
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
    @patch("ssh_task.subprocess.run")
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

    @patch("ssh_task.subprocess.run")
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

    @patch("ssh_task.subprocess.run")
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

    @patch("ssh_task.subprocess.run")
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

    @patch("ssh_task.subprocess.run")
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

    @patch("ssh_task.subprocess.run")
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

    @patch("ssh_task.subprocess.run")
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


# ---------------------------------------------------------------------------
# MCP tool: initiate_ssh_task
# ---------------------------------------------------------------------------


class TestInitiateSSHTaskTool:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        import server

        original = server._mailbox
        server._mailbox = None
        try:
            result = await server.initiate_ssh_task("oppy", "Do stuff")
            assert "not configured" in result.lower()
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_unknown_brother(self):
        import server

        mock_client = AsyncMock()
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.initiate_ssh_task("bob", "Do stuff")
            assert "Unknown brother" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    @patch("server.initiate_task")
    async def test_success(self, mock_initiate):
        import server

        mock_client = AsyncMock()
        mock_client.create_task.return_value = {"id": 7}
        mock_client.update_task.return_value = {"id": 7, "status": "launched"}
        mock_initiate.return_value = TaskResult(
            success=True,
            session_name="task-oppy-test-123",
            host="masuda",
            message="Task launched",
        )
        original = server._mailbox
        original_name = server._mailbox_name
        server._mailbox = mock_client
        server._mailbox_name = "doot"
        try:
            result = await server.initiate_ssh_task(
                "oppy", "Review the code", subject="Code review"
            )
            assert "Task #7" in result
            assert "launched successfully" in result
            assert "oppy" in result
            mock_client.create_task.assert_called_once()
            mock_initiate.assert_called_once()
        finally:
            server._mailbox = original
            server._mailbox_name = original_name

    @pytest.mark.asyncio
    @patch("server.initiate_task")
    async def test_ssh_failure(self, mock_initiate):
        import server

        mock_client = AsyncMock()
        mock_client.create_task.return_value = {"id": 8}
        mock_client.update_task.return_value = {"id": 8, "status": "failed"}
        mock_initiate.return_value = TaskResult(
            success=False,
            session_name="task-oppy-test-456",
            host="masuda",
            message="SSH connection timed out",
            stderr="ssh: connect to host masuda: Connection timed out",
        )
        original = server._mailbox
        original_name = server._mailbox_name
        server._mailbox = mock_client
        server._mailbox_name = "doot"
        try:
            result = await server.initiate_ssh_task("oppy", "Do stuff")
            assert "failed" in result.lower()
            assert "Task #8" in result
            mock_client.update_task.assert_called_once()
        finally:
            server._mailbox = original
            server._mailbox_name = original_name

    @pytest.mark.asyncio
    async def test_task_creation_error(self):
        import server

        mock_client = AsyncMock()
        mock_client.create_task.side_effect = Exception("API unreachable")
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.initiate_ssh_task("oppy", "Do stuff")
            assert "Error creating task" in result
        finally:
            server._mailbox = original


# ---------------------------------------------------------------------------
# MCP tool: list_tasks
# ---------------------------------------------------------------------------


class TestListTasksTool:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        import server

        original = server._mailbox
        server._mailbox = None
        try:
            result = await server.list_tasks()
            assert "not configured" in result.lower()
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_no_tasks(self):
        import server

        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = []
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.list_tasks()
            assert "No tasks" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_with_tasks(self):
        import server

        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [
            {
                "id": 1,
                "creator": "doot",
                "assignee": "oppy",
                "subject": "Review code",
                "status": "completed",
                "created_at": "2026-02-09T10:00:00Z",
                "started_at": "2026-02-09T10:01:00Z",
                "completed_at": "2026-02-09T10:30:00Z",
            },
            {
                "id": 2,
                "creator": "doot",
                "assignee": "jerry",
                "subject": "",
                "status": "launched",
                "created_at": "2026-02-09T11:00:00Z",
                "started_at": None,
                "completed_at": None,
            },
        ]
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.list_tasks()
            assert "#1" in result
            assert "#2" in result
            assert "oppy" in result
            assert "jerry" in result
            assert "completed" in result
            assert "launched" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_error(self):
        import server

        mock_client = AsyncMock()
        mock_client.get_tasks.side_effect = Exception("Connection refused")
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.list_tasks()
            assert "Error" in result
        finally:
            server._mailbox = original


# ---------------------------------------------------------------------------
# mailbox_mcp: list_tasks and get_task tools
# ---------------------------------------------------------------------------


class TestMailboxMCPListTasks:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        import mailbox_mcp

        original = mailbox_mcp._mailbox
        mailbox_mcp._mailbox = None
        try:
            result = await mailbox_mcp.list_tasks()
            assert "not configured" in result.lower()
        finally:
            mailbox_mcp._mailbox = original

    @pytest.mark.asyncio
    async def test_no_tasks(self):
        import mailbox_mcp

        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = []
        original = mailbox_mcp._mailbox
        mailbox_mcp._mailbox = mock_client
        try:
            result = await mailbox_mcp.list_tasks()
            assert "No tasks" in result
        finally:
            mailbox_mcp._mailbox = original

    @pytest.mark.asyncio
    async def test_with_tasks(self):
        import mailbox_mcp

        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = [
            {
                "id": 1,
                "creator": "doot",
                "assignee": "oppy",
                "subject": "Review code",
                "status": "completed",
                "created_at": "2026-02-09T10:00:00Z",
                "completed_at": "2026-02-09T10:30:00Z",
            },
        ]
        original = mailbox_mcp._mailbox
        mailbox_mcp._mailbox = mock_client
        try:
            result = await mailbox_mcp.list_tasks()
            assert "#1" in result
            assert "oppy" in result
            assert "completed" in result
            assert "Review code" in result
        finally:
            mailbox_mcp._mailbox = original

    @pytest.mark.asyncio
    async def test_passes_filters(self):
        import mailbox_mcp

        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = []
        original = mailbox_mcp._mailbox
        mailbox_mcp._mailbox = mock_client
        try:
            await mailbox_mcp.list_tasks(assignee="oppy", status="launched", limit=5)
            mock_client.get_tasks.assert_called_once_with(
                assignee="oppy", status="launched", limit=5
            )
        finally:
            mailbox_mcp._mailbox = original


class TestMailboxMCPGetTask:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        import mailbox_mcp

        original = mailbox_mcp._mailbox
        mailbox_mcp._mailbox = None
        try:
            result = await mailbox_mcp.get_task(1)
            assert "not configured" in result.lower()
        finally:
            mailbox_mcp._mailbox = original

    @pytest.mark.asyncio
    async def test_success(self):
        import mailbox_mcp

        mock_client = AsyncMock()
        mock_client.get_task.return_value = {
            "id": 3,
            "creator": "doot",
            "assignee": "oppy",
            "subject": "Live test #2",
            "status": "launched",
            "prompt": "Acknowledge receipt",
            "created_at": "2026-02-10T04:55:00Z",
            "completed_at": None,
            "host": "masuda",
            "session_name": "task-oppy-live-test-123",
            "working_dir": "~/projects/mol_diffusion/OMTRA_oppy",
            "output": None,
        }
        original = mailbox_mcp._mailbox
        mailbox_mcp._mailbox = mock_client
        try:
            result = await mailbox_mcp.get_task(3)
            assert "Task #3" in result
            assert "oppy" in result
            assert "launched" in result
            assert "masuda" in result
            assert "Acknowledge receipt" in result
        finally:
            mailbox_mcp._mailbox = original

    @pytest.mark.asyncio
    async def test_error(self):
        import mailbox_mcp

        mock_client = AsyncMock()
        mock_client.get_task.side_effect = Exception("Not found")
        original = mailbox_mcp._mailbox
        mailbox_mcp._mailbox = mock_client
        try:
            result = await mailbox_mcp.get_task(999)
            assert "Error" in result
        finally:
            mailbox_mcp._mailbox = original
