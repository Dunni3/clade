"""Tests for the task system: database, API, client, and MCP tools."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

os.environ.setdefault("MAILBOX_API_KEYS", "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry")

from httpx import ASGITransport, AsyncClient
from mcp.server.fastmcp import FastMCP

from mailbox.app import app
from mailbox import db as mailbox_db
from terminal_spawner.communication.mailbox_client import MailboxClient
from terminal_spawner.mcp.tools.mailbox_tools import create_mailbox_tools
from terminal_spawner.mcp.tools.task_tools import create_task_tools
from terminal_spawner.tasks.ssh_task import TaskResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}
JERRY_HEADERS = {"Authorization": "Bearer test-key-jerry"}


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Use a fresh SQLite database for each test."""
    db_path = str(tmp_path / "test.db")
    original = mailbox_db.DB_PATH
    mailbox_db.DB_PATH = db_path
    await mailbox_db.init_db()
    yield db_path
    mailbox_db.DB_PATH = original


@pytest_asyncio.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_mailbox_tools(mailbox):
    """Create mailbox tools with the given mailbox client."""
    mcp = FastMCP("test")
    return create_mailbox_tools(mcp, mailbox)


TEST_CONFIG = {
    "brothers": {
        "oppy": {
            "host": "masuda",
            "working_dir": "~/projects/mol_diffusion/OMTRA_oppy",
            "command": "ssh -t masuda \"bash -lc 'cd ~/projects/mol_diffusion/OMTRA_oppy && claude'\"",
            "description": "Brother Oppy — The architect on masuda",
        },
        "jerry": {
            "host": "cluster",
            "working_dir": None,
            "command": 'ssh -t cluster "bash -lc claude"',
            "description": "Brother Jerry — GPU jobs on the cluster",
        },
    },
}


def _make_task_tools(mailbox):
    """Create task delegation tools with the given mailbox client."""
    mcp = FastMCP("test")
    return create_task_tools(mcp, mailbox, TEST_CONFIG)


# ---------------------------------------------------------------------------
# Tasks — database layer
# ---------------------------------------------------------------------------


class TestDatabaseTasks:
    @pytest.mark.asyncio
    async def test_insert_and_get_task(self):
        task_id = await mailbox_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="Review the code",
            subject="Code review",
            session_name="task-oppy-review-123",
            host="masuda",
            working_dir="~/projects/test",
        )
        assert task_id > 0

        task = await mailbox_db.get_task(task_id)
        assert task is not None
        assert task["creator"] == "doot"
        assert task["assignee"] == "oppy"
        assert task["prompt"] == "Review the code"
        assert task["subject"] == "Code review"
        assert task["status"] == "pending"
        assert task["session_name"] == "task-oppy-review-123"
        assert task["host"] == "masuda"
        assert task["working_dir"] == "~/projects/test"
        assert task["messages"] == []

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        task = await mailbox_db.get_task(999)
        assert task is None

    @pytest.mark.asyncio
    async def test_get_tasks_all(self):
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Task 2"
        )
        tasks = await mailbox_db.get_tasks()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_get_tasks_filter_assignee(self):
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Task 2"
        )
        tasks = await mailbox_db.get_tasks(assignee="oppy")
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_get_tasks_filter_status(self):
        t1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Task 2"
        )
        await mailbox_db.update_task(t1, status="completed")
        tasks = await mailbox_db.get_tasks(status="pending")
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "jerry"

    @pytest.mark.asyncio
    async def test_get_tasks_filter_creator(self):
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="ian", assignee="oppy", prompt="Task 2"
        )
        tasks = await mailbox_db.get_tasks(creator="ian")
        assert len(tasks) == 1
        assert tasks[0]["creator"] == "ian"

    @pytest.mark.asyncio
    async def test_get_tasks_limit(self):
        for i in range(5):
            await mailbox_db.insert_task(
                creator="doot", assignee="oppy", prompt=f"Task {i}"
            )
        tasks = await mailbox_db.get_tasks(limit=3)
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_update_task_status(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Test"
        )
        updated = await mailbox_db.update_task(task_id, status="in_progress")
        assert updated is not None
        assert updated["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_task_output(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Test"
        )
        updated = await mailbox_db.update_task(
            task_id, status="completed", output="All done"
        )
        assert updated["status"] == "completed"
        assert updated["output"] == "All done"

    @pytest.mark.asyncio
    async def test_update_task_not_found(self):
        result = await mailbox_db.update_task(999, status="completed")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task_timestamps(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Test"
        )
        updated = await mailbox_db.update_task(
            task_id,
            status="completed",
            started_at="2026-02-09T10:00:00Z",
            completed_at="2026-02-09T10:30:00Z",
        )
        assert updated["started_at"] == "2026-02-09T10:00:00Z"
        assert updated["completed_at"] == "2026-02-09T10:30:00Z"


class TestDatabaseTaskLinkedMessages:
    @pytest.mark.asyncio
    async def test_message_with_task_id(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        msg_id = await mailbox_db.insert_message(
            sender="oppy",
            subject="Task received",
            body="I got it",
            recipients=["doot"],
            task_id=task_id,
        )
        task = await mailbox_db.get_task(task_id)
        assert len(task["messages"]) == 1
        assert task["messages"][0]["id"] == msg_id
        assert task["messages"][0]["body"] == "I got it"

    @pytest.mark.asyncio
    async def test_multiple_linked_messages(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        await mailbox_db.insert_message(
            sender="oppy", subject="Started", body="Working on it",
            recipients=["doot"], task_id=task_id,
        )
        await mailbox_db.insert_message(
            sender="oppy", subject="Done", body="All finished",
            recipients=["doot"], task_id=task_id,
        )
        task = await mailbox_db.get_task(task_id)
        assert len(task["messages"]) == 2

    @pytest.mark.asyncio
    async def test_message_without_task_id(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Hi", body="Hello", recipients=["oppy"]
        )
        assert msg_id > 0

    @pytest.mark.asyncio
    async def test_linked_messages_include_recipients(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        await mailbox_db.insert_message(
            sender="oppy", subject="Status", body="Update",
            recipients=["doot", "jerry"], task_id=task_id,
        )
        task = await mailbox_db.get_task(task_id)
        assert set(task["messages"][0]["recipients"]) == {"doot", "jerry"}


# ---------------------------------------------------------------------------
# Tasks — API endpoints
# ---------------------------------------------------------------------------


class TestAPITasks:
    @pytest.mark.asyncio
    async def test_create_task(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Review the code",
                "subject": "Code review",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["message"] == "Task created"

    @pytest.mark.asyncio
    async def test_create_task_no_auth(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_tasks(self, client):
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Task 1", "subject": "First"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "Task 2", "subject": "Second"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get("/api/v1/tasks", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_filter_assignee(self, client):
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Task 1"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "Task 2"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get(
            "/api/v1/tasks", params={"assignee": "oppy"}, headers=DOOT_HEADERS
        )
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_list_tasks_filter_status(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Task 1"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "Task 2"},
            headers=DOOT_HEADERS,
        )
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get(
            "/api/v1/tasks", params={"status": "pending"}, headers=DOOT_HEADERS
        )
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "jerry"

    @pytest.mark.asyncio
    async def test_get_task_detail(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Do the thing",
                "subject": "Test task",
                "session_name": "task-oppy-test-123",
                "host": "masuda",
                "working_dir": "~/projects/test",
            },
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["creator"] == "doot"
        assert data["assignee"] == "oppy"
        assert data["prompt"] == "Do the thing"
        assert data["session_name"] == "task-oppy-test-123"
        assert data["messages"] == []

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, client):
        resp = await client.get("/api/v1/tasks/999", headers=DOOT_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_task_status(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"
        assert resp.json()["started_at"] is not None

    @pytest.mark.asyncio
    async def test_update_task_completed_sets_timestamp(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "All done"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        assert data["output"] == "All done"

    @pytest.mark.asyncio
    async def test_update_task_forbidden(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=JERRY_HEADERS,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_task_creator_can_update(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "cancelled"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_task_with_linked_messages(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        await client.post(
            "/api/v1/messages",
            json={
                "recipients": ["doot"],
                "body": "Task received",
                "subject": "Ack",
                "task_id": task_id,
            },
            headers=OPPY_HEADERS,
        )

        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        data = resp.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["body"] == "Task received"


# ---------------------------------------------------------------------------
# MailboxClient — task methods
# ---------------------------------------------------------------------------


class TestMailboxClientTasks:
    def setup_method(self):
        self.client = MailboxClient("http://localhost:8000", "test-key")

    def _make_mock_resp(self, json_data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def _make_async_client(self, get_resp=None, post_resp=None, patch_resp=None):
        instance = AsyncMock()
        if get_resp is not None:
            instance.get.return_value = get_resp
        if post_resp is not None:
            instance.post.return_value = post_resp
        if patch_resp is not None:
            instance.patch.return_value = patch_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        return instance

    @pytest.mark.asyncio
    async def test_create_task(self):
        mock_resp = self._make_mock_resp({"id": 1, "message": "Task created"})
        with patch("terminal_spawner.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.create_task("oppy", "Do stuff", subject="Test")
            assert result["id"] == 1
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tasks(self):
        mock_resp = self._make_mock_resp([
            {"id": 1, "creator": "doot", "assignee": "oppy", "subject": "Test",
             "status": "pending", "created_at": "2026-02-09T10:00:00Z",
             "started_at": None, "completed_at": None}
        ])
        with patch("terminal_spawner.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.get_tasks(assignee="oppy")
            assert len(result) == 1
            assert result[0]["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_get_task(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "creator": "doot", "assignee": "oppy", "subject": "Test",
            "prompt": "Do stuff", "status": "pending",
            "created_at": "2026-02-09T10:00:00Z",
            "started_at": None, "completed_at": None,
            "session_name": None, "host": None, "working_dir": None,
            "output": None, "messages": [],
        })
        with patch("terminal_spawner.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.get_task(1)
            assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_update_task(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "creator": "doot", "assignee": "oppy", "subject": "Test",
            "prompt": "Do stuff", "status": "completed",
            "created_at": "2026-02-09T10:00:00Z",
            "started_at": "2026-02-09T10:01:00Z",
            "completed_at": "2026-02-09T10:30:00Z",
            "session_name": None, "host": None, "working_dir": None,
            "output": "All done", "messages": [],
        })
        with patch("terminal_spawner.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(patch_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.update_task(1, status="completed", output="All done")
            assert result["status"] == "completed"
            instance.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_with_task_id(self):
        mock_resp = self._make_mock_resp({"id": 5, "message": "Message sent"})
        with patch("terminal_spawner.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.send_message(
                ["doot"], "Task done", subject="Done", task_id=3
            )
            assert result["id"] == 5
            call_kwargs = instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["task_id"] == 3


# ---------------------------------------------------------------------------
# MCP tools — task delegation (initiate_ssh_task, list_tasks)
# ---------------------------------------------------------------------------


class TestInitiateSSHTaskTool:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_task_tools(None)
        result = await tools["initiate_ssh_task"]("oppy", "Do stuff")
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_brother(self):
        mock_client = AsyncMock()
        tools = _make_task_tools(mock_client)
        result = await tools["initiate_ssh_task"]("bob", "Do stuff")
        assert "Unknown brother" in result

    @pytest.mark.asyncio
    @patch("terminal_spawner.mcp.tools.task_tools.initiate_task")
    async def test_success(self, mock_initiate):
        mock_client = AsyncMock()
        mock_client.create_task.return_value = {"id": 7}
        mock_client.update_task.return_value = {"id": 7, "status": "launched"}
        mock_initiate.return_value = TaskResult(
            success=True,
            session_name="task-oppy-test-123",
            host="masuda",
            message="Task launched",
        )
        tools = _make_task_tools(mock_client)
        result = await tools["initiate_ssh_task"](
            "oppy", "Review the code", subject="Code review"
        )
        assert "Task #7" in result
        assert "launched successfully" in result
        assert "oppy" in result
        mock_client.create_task.assert_called_once()
        mock_initiate.assert_called_once()

    @pytest.mark.asyncio
    @patch("terminal_spawner.mcp.tools.task_tools.initiate_task")
    async def test_ssh_failure(self, mock_initiate):
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
        tools = _make_task_tools(mock_client)
        result = await tools["initiate_ssh_task"]("oppy", "Do stuff")
        assert "failed" in result.lower()
        assert "Task #8" in result
        mock_client.update_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_creation_error(self):
        mock_client = AsyncMock()
        mock_client.create_task.side_effect = Exception("API unreachable")
        tools = _make_task_tools(mock_client)
        result = await tools["initiate_ssh_task"]("oppy", "Do stuff")
        assert "Error creating task" in result


class TestListTasksTool:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_mailbox_tools(None)
        result = await tools["list_tasks"]()
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_no_tasks(self):
        mock_client = AsyncMock()
        mock_client.get_tasks.return_value = []
        tools = _make_mailbox_tools(mock_client)
        result = await tools["list_tasks"]()
        assert "No tasks" in result

    @pytest.mark.asyncio
    async def test_with_tasks(self):
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
        tools = _make_mailbox_tools(mock_client)
        result = await tools["list_tasks"]()
        assert "#1" in result
        assert "#2" in result
        assert "oppy" in result
        assert "jerry" in result
        assert "completed" in result
        assert "launched" in result

    @pytest.mark.asyncio
    async def test_error(self):
        mock_client = AsyncMock()
        mock_client.get_tasks.side_effect = Exception("Connection refused")
        tools = _make_mailbox_tools(mock_client)
        result = await tools["list_tasks"]()
        assert "Error" in result
