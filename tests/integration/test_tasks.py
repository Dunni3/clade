"""Tests for the task system: database, API, client, and MCP tools."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

os.environ.setdefault("MAILBOX_API_KEYS", "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian")

from httpx import ASGITransport, AsyncClient
from mcp.server.fastmcp import FastMCP

from hearth.app import app
from hearth import db as mailbox_db
from clade.communication.mailbox_client import MailboxClient
from clade.mcp.tools.mailbox_tools import create_mailbox_tools
from clade.mcp.tools.task_tools import create_task_tools
from clade.tasks.ssh_task import TaskResult


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


def _make_task_tools(mailbox, mailbox_url="https://test.example.com", mailbox_api_key="test-key"):
    """Create task delegation tools with the given mailbox client."""
    mcp = FastMCP("test")
    return create_task_tools(mcp, mailbox, TEST_CONFIG, mailbox_url=mailbox_url, mailbox_api_key=mailbox_api_key)


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


class TestDatabaseTaskTrees:
    @pytest.mark.asyncio
    async def test_insert_with_parent(self):
        parent_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Parent task", subject="Parent"
        )
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Child task", subject="Child",
            parent_task_id=parent_id,
        )

        child = await mailbox_db.get_task(child_id)
        assert child["parent_task_id"] == parent_id
        assert child["root_task_id"] == parent_id

    @pytest.mark.asyncio
    async def test_three_level_chain(self):
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        mid_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Mid", subject="Mid",
            parent_task_id=root_id,
        )
        leaf_id = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Leaf", subject="Leaf",
            parent_task_id=mid_id,
        )

        leaf = await mailbox_db.get_task(leaf_id)
        assert leaf["parent_task_id"] == mid_id
        assert leaf["root_task_id"] == root_id  # inherits root, not parent

    @pytest.mark.asyncio
    async def test_invalid_parent_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            await mailbox_db.insert_task(
                creator="doot", assignee="oppy", prompt="Orphan",
                parent_task_id=999,
            )

    @pytest.mark.asyncio
    async def test_get_task_includes_children(self):
        parent_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Parent", subject="Parent"
        )
        c1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Child 1",
            parent_task_id=parent_id,
        )
        c2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Child 2",
            parent_task_id=parent_id,
        )

        parent = await mailbox_db.get_task(parent_id)
        assert len(parent["children"]) == 2
        child_ids = {c["id"] for c in parent["children"]}
        assert child_ids == {c1, c2}

    @pytest.mark.asyncio
    async def test_get_tree(self):
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        c1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C1", parent_task_id=root_id,
        )
        c2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="C2", parent_task_id=root_id,
        )
        c1_1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C1.1", parent_task_id=c1,
        )

        tree = await mailbox_db.get_tree(root_id)
        assert tree["id"] == root_id
        assert len(tree["children"]) == 2
        # Find c1 in children
        c1_node = next(c for c in tree["children"] if c["id"] == c1)
        assert len(c1_node["children"]) == 1
        assert c1_node["children"][0]["id"] == c1_1

    @pytest.mark.asyncio
    async def test_get_tree_not_found(self):
        tree = await mailbox_db.get_tree(999)
        assert tree is None

    @pytest.mark.asyncio
    async def test_get_trees_with_stats(self):
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        c1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C1", parent_task_id=root_id,
        )
        c2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="C2", parent_task_id=root_id,
        )
        await mailbox_db.update_task(c1, status="completed")
        await mailbox_db.update_task(c2, status="failed")

        trees = await mailbox_db.get_trees()
        assert len(trees) == 1
        t = trees[0]
        assert t["root_task_id"] == root_id
        assert t["total_tasks"] == 3  # root + 2 children
        assert t["completed"] == 1
        assert t["failed"] == 1
        assert t["pending"] == 1  # root is still pending

    @pytest.mark.asyncio
    async def test_standalone_task_is_own_root(self):
        """Tasks without parent are their own root (single-node tree)."""
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Standalone"
        )
        task = await mailbox_db.get_task(task_id)
        assert task["parent_task_id"] is None
        assert task["root_task_id"] == task_id
        assert task["children"] == []


class TestDatabaseGetApiKeyForName:
    @pytest.mark.asyncio
    async def test_found(self):
        await mailbox_db.insert_api_key("testbot", "secret-key-123")
        key = await mailbox_db.get_api_key_for_name("testbot")
        assert key == "secret-key-123"

    @pytest.mark.asyncio
    async def test_not_found(self):
        key = await mailbox_db.get_api_key_for_name("nobody")
        assert key is None


class TestDatabaseTreesKilledCount:
    @pytest.mark.asyncio
    async def test_killed_count_in_tree_stats(self):
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        c1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C1", parent_task_id=root_id,
        )
        c2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="C2", parent_task_id=root_id,
        )
        await mailbox_db.update_task(c1, status="killed")
        await mailbox_db.update_task(c2, status="completed")

        trees = await mailbox_db.get_trees()
        assert len(trees) == 1
        t = trees[0]
        assert t["killed"] == 1
        assert t["completed"] == 1


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
# Tasks — API tree endpoints
# ---------------------------------------------------------------------------


class TestAPITaskTrees:
    @pytest.mark.asyncio
    async def test_create_with_parent(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Parent", "subject": "Parent"},
            headers=DOOT_HEADERS,
        )
        parent_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Child",
                "parent_task_id": parent_id,
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        child_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{child_id}", headers=DOOT_HEADERS)
        data = resp.json()
        assert data["parent_task_id"] == parent_id
        assert data["root_task_id"] == parent_id

    @pytest.mark.asyncio
    async def test_create_invalid_parent_422(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Orphan",
                "parent_task_id": 9999,
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_task_detail_includes_children(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Parent", "subject": "Parent"},
            headers=DOOT_HEADERS,
        )
        parent_id = resp.json()["id"]

        await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Child 1", "parent_task_id": parent_id},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "Child 2", "parent_task_id": parent_id},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(f"/api/v1/tasks/{parent_id}", headers=DOOT_HEADERS)
        data = resp.json()
        assert len(data["children"]) == 2

    @pytest.mark.asyncio
    async def test_tree_list(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Root", "subject": "Root task"},
            headers=DOOT_HEADERS,
        )
        root_id = resp.json()["id"]
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Child", "parent_task_id": root_id},
            headers=DOOT_HEADERS,
        )

        resp = await client.get("/api/v1/trees", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        trees = resp.json()
        assert len(trees) == 1
        assert trees[0]["root_task_id"] == root_id
        assert trees[0]["total_tasks"] == 2

    @pytest.mark.asyncio
    async def test_tree_detail(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Root", "subject": "Root"},
            headers=DOOT_HEADERS,
        )
        root_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "C1", "parent_task_id": root_id},
            headers=DOOT_HEADERS,
        )
        c1_id = resp.json()["id"]

        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "C1.1", "parent_task_id": c1_id},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(f"/api/v1/trees/{root_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        tree = resp.json()
        assert tree["id"] == root_id
        assert len(tree["children"]) == 1
        assert tree["children"][0]["id"] == c1_id
        assert len(tree["children"][0]["children"]) == 1

    @pytest.mark.asyncio
    async def test_tree_not_found(self, client):
        resp = await client.get("/api/v1/trees/999", headers=DOOT_HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Kill task — API endpoint
# ---------------------------------------------------------------------------


class TestAPIKillTask:
    @pytest.mark.asyncio
    async def test_kill_in_progress_task(self, client):
        """Kill an in_progress task — should return 200 with status=killed."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Move to in_progress
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/kill",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "killed"
        assert data["completed_at"] is not None
        assert "Killed by doot" in data["output"]

    @pytest.mark.asyncio
    async def test_kill_pending_task(self, client):
        """Kill a pending task — should work since it's an active status."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/kill",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "killed"

    @pytest.mark.asyncio
    async def test_kill_completed_task_409(self, client):
        """Cannot kill an already-completed task."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=OPPY_HEADERS,
        )

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/kill",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_kill_by_non_creator_403(self, client):
        """Only creator or admins can kill a task."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/kill",
            headers=JERRY_HEADERS,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_kill_not_found(self, client):
        """Killing a non-existent task returns 404."""
        resp = await client.post(
            "/api/v1/tasks/9999/kill",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_kill_already_killed_409(self, client):
        """Cannot kill a task that's already killed."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Kill it once
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/kill",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200

        # Try to kill again — should be 409
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/kill",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_killed_sets_completed_at_via_patch(self, client):
        """PATCH update_task with status=killed also sets completed_at."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "killed"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "killed"
        assert data["completed_at"] is not None


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
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
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
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
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
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
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
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(patch_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.update_task(1, status="completed", output="All done")
            assert result["status"] == "completed"
            instance.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_kill_task(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "creator": "doot", "assignee": "oppy", "subject": "Test",
            "prompt": "Do stuff", "status": "killed",
            "created_at": "2026-02-09T10:00:00Z",
            "started_at": "2026-02-09T10:01:00Z",
            "completed_at": "2026-02-09T10:30:00Z",
            "session_name": None, "host": None, "working_dir": None,
            "output": "Killed by doot", "messages": [],
        })
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.kill_task(1)
            assert result["status"] == "killed"
            instance.post.assert_called_once()
            call_args = instance.post.call_args
            assert "/tasks/1/kill" in str(call_args)

    @pytest.mark.asyncio
    async def test_send_message_with_task_id(self):
        mock_resp = self._make_mock_resp({"id": 5, "message": "Message sent"})
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
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
    @patch("clade.mcp.tools.task_tools.initiate_task")
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
    @patch("clade.mcp.tools.task_tools.initiate_task")
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

    @pytest.mark.asyncio
    @patch("clade.mcp.tools.task_tools.initiate_task")
    async def test_passes_mailbox_credentials_for_hooks(self, mock_initiate):
        mock_client = AsyncMock()
        mock_client.create_task.return_value = {"id": 10}
        mock_client.update_task.return_value = {"id": 10, "status": "launched"}
        mock_initiate.return_value = TaskResult(
            success=True,
            session_name="task-oppy-test-789",
            host="masuda",
            message="Task launched",
        )
        tools = _make_task_tools(
            mock_client,
            mailbox_url="https://54.84.119.14",
            mailbox_api_key="secret-key",
        )
        await tools["initiate_ssh_task"]("oppy", "Do stuff", subject="Test")
        call_kwargs = mock_initiate.call_args.kwargs
        assert call_kwargs["task_id"] == 10
        assert call_kwargs["mailbox_url"] == "https://54.84.119.14"
        assert call_kwargs["mailbox_api_key"] == "secret-key"


class TestKillTaskTool:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_mailbox_tools(None)
        result = await tools["kill_task"](1)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        mock_client = AsyncMock()
        mock_client.kill_task.return_value = {
            "id": 5, "status": "killed", "assignee": "oppy",
        }
        tools = _make_mailbox_tools(mock_client)
        result = await tools["kill_task"](5)
        assert "Task #5 killed" in result
        assert "oppy" in result

    @pytest.mark.asyncio
    async def test_error(self):
        mock_client = AsyncMock()
        mock_client.kill_task.side_effect = Exception("Connection refused")
        tools = _make_mailbox_tools(mock_client)
        result = await tools["kill_task"](1)
        assert "Error" in result


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


# ---------------------------------------------------------------------------
# Task Events — database layer
# ---------------------------------------------------------------------------


class TestDatabaseTaskEvents:
    @pytest.mark.asyncio
    async def test_insert_and_get_events(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        ev1 = await mailbox_db.insert_task_event(
            task_id, event_type="PostToolUse", summary="ran: npm test", tool_name="Bash"
        )
        ev2 = await mailbox_db.insert_task_event(
            task_id, event_type="PostToolUse", summary="edited: src/main.py", tool_name="Edit"
        )
        assert ev1 > 0
        assert ev2 > ev1

        events = await mailbox_db.get_task_events(task_id)
        assert len(events) == 2
        assert events[0]["event_type"] == "PostToolUse"
        assert events[0]["tool_name"] == "Bash"
        assert events[0]["summary"] == "ran: npm test"
        assert events[1]["tool_name"] == "Edit"

    @pytest.mark.asyncio
    async def test_events_empty_for_new_task(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        events = await mailbox_db.get_task_events(task_id)
        assert events == []

    @pytest.mark.asyncio
    async def test_events_included_in_get_task(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        await mailbox_db.insert_task_event(
            task_id, event_type="PostToolUse", summary="ran: ls", tool_name="Bash"
        )
        await mailbox_db.insert_task_event(
            task_id, event_type="Stop", summary="Session ended"
        )
        task = await mailbox_db.get_task(task_id)
        assert "events" in task
        assert len(task["events"]) == 2
        assert task["events"][0]["summary"] == "ran: ls"
        assert task["events"][1]["event_type"] == "Stop"
        assert task["events"][1]["tool_name"] is None

    @pytest.mark.asyncio
    async def test_event_null_tool_name(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        ev_id = await mailbox_db.insert_task_event(
            task_id, event_type="Stop", summary="Session ended", tool_name=None
        )
        events = await mailbox_db.get_task_events(task_id)
        assert len(events) == 1
        assert events[0]["tool_name"] is None


# ---------------------------------------------------------------------------
# Task Events — API endpoints
# ---------------------------------------------------------------------------


class TestAPITaskEvents:
    @pytest.mark.asyncio
    async def test_log_event(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={
                "event_type": "PostToolUse",
                "tool_name": "Bash",
                "summary": "ran: pytest tests/",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_type"] == "PostToolUse"
        assert data["tool_name"] == "Bash"
        assert data["summary"] == "ran: pytest tests/"
        assert data["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_log_event_no_tool_name(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "Stop", "summary": "Session ended"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_name"] is None

    @pytest.mark.asyncio
    async def test_log_event_task_not_found(self, client):
        resp = await client.post(
            "/api/v1/tasks/9999/log",
            json={"event_type": "Stop", "summary": "Session ended"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_log_event_no_auth(self, client):
        resp = await client.post(
            "/api/v1/tasks/1/log",
            json={"event_type": "Stop", "summary": "Session ended"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_events_in_task_detail(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "PostToolUse", "tool_name": "Bash", "summary": "ran: ls"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "PostToolUse", "tool_name": "Edit", "summary": "edited: main.py"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "Stop", "summary": "Session ended"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        task = resp.json()
        assert len(task["events"]) == 3
        assert task["events"][0]["tool_name"] == "Bash"
        assert task["events"][2]["event_type"] == "Stop"

    @pytest.mark.asyncio
    async def test_log_event_validation(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Missing required 'summary' field
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "PostToolUse"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422
