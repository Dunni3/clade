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

    @pytest.mark.asyncio
    async def test_depth_computed_on_insert(self):
        """Root task has depth 0, children depth 1, grandchildren depth 2."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Child",
            parent_task_id=root_id,
        )
        grandchild_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Grandchild",
            parent_task_id=child_id,
        )

        root = await mailbox_db.get_task(root_id)
        child = await mailbox_db.get_task(child_id)
        grandchild = await mailbox_db.get_task(grandchild_id)
        assert root["depth"] == 0
        assert child["depth"] == 1
        assert grandchild["depth"] == 2

    @pytest.mark.asyncio
    async def test_depth_in_tree(self):
        """get_tree returns correct depth at each level."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        c1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C1", parent_task_id=root_id,
        )
        c1_1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C1.1", parent_task_id=c1,
        )

        tree = await mailbox_db.get_tree(root_id)
        assert tree["depth"] == 0
        assert tree["children"][0]["depth"] == 1
        assert tree["children"][0]["children"][0]["depth"] == 2

    @pytest.mark.asyncio
    async def test_metadata_round_trip(self):
        """Metadata dict is stored as JSON and returned parsed."""
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root",
            metadata={"max_depth": 10, "strategy": "conservative"},
        )
        task = await mailbox_db.get_task(task_id)
        assert task["metadata"] == {"max_depth": 10, "strategy": "conservative"}

    @pytest.mark.asyncio
    async def test_metadata_none_by_default(self):
        """Tasks without metadata have metadata=None."""
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="No metadata"
        )
        task = await mailbox_db.get_task(task_id)
        assert task["metadata"] is None

    @pytest.mark.asyncio
    async def test_metadata_in_tree(self):
        """get_tree parses metadata JSON on root and descendants."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root",
            metadata={"max_depth": 15},
        )
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Child",
            parent_task_id=root_id,
        )
        tree = await mailbox_db.get_tree(root_id)
        assert tree["metadata"] == {"max_depth": 15}
        assert tree["children"][0]["metadata"] is None

    @pytest.mark.asyncio
    async def test_depth_cascades_on_reparent(self):
        """Reparenting updates depth for task and all descendants."""
        a = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="A", subject="A"
        )
        b = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="B", parent_task_id=a
        )
        c = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C", parent_task_id=b
        )
        # B is depth 1, C is depth 2

        # Create new root D
        d = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="D", subject="D"
        )
        e = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="E", parent_task_id=d
        )
        # E is depth 1

        # Reparent B under E (so B goes from depth 1 to depth 2)
        await mailbox_db.update_task_parent(b, e)

        task_b = await mailbox_db.get_task(b)
        task_c = await mailbox_db.get_task(c)
        assert task_b["depth"] == 2  # was 1, now under E (depth 1)
        assert task_c["depth"] == 3  # was 2, shifted by +1


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


class TestDatabaseMultiParentTasks:
    """Tests for multi-parent (DAG) task support via task_parents join table."""

    @pytest.mark.asyncio
    async def test_insert_with_parent_task_ids(self):
        """parent_task_ids creates entries in task_parents join table."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        p1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="P1", parent_task_id=root_id,
        )
        p2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="P2", parent_task_id=root_id,
        )
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Child",
            parent_task_ids=[p1, p2],
        )

        child = await mailbox_db.get_task(child_id)
        assert child["parent_task_id"] == p1  # primary parent = first in list
        assert child["root_task_id"] == root_id
        assert child["parent_task_ids"] == [p1, p2]

    @pytest.mark.asyncio
    async def test_depth_from_deepest_parent(self):
        """Depth is max(parent depths) + 1 when parents are at different depths."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        shallow = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Shallow", parent_task_id=root_id,
        )
        mid = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Mid", parent_task_id=shallow,
        )
        deep = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Deep", parent_task_id=mid,
        )
        # Join shallow (depth=1) and deep (depth=3) → child depth should be 4
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Join",
            parent_task_ids=[shallow, deep],
        )
        child = await mailbox_db.get_task(child_id)
        assert child["depth"] == 4  # max(1, 3) + 1

    @pytest.mark.asyncio
    async def test_cross_tree_join_rejected(self):
        """Parents from different trees are rejected."""
        tree_a_root = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Tree A root",
        )
        tree_b_root = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Tree B root",
        )
        with pytest.raises(ValueError, match="Cross-tree joins not supported"):
            await mailbox_db.insert_task(
                creator="doot", assignee="oppy", prompt="Cross-tree child",
                parent_task_ids=[tree_a_root, tree_b_root],
            )

    @pytest.mark.asyncio
    async def test_get_task_parent_ids(self):
        """get_task_parent_ids returns all parents in insertion order."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root",
        )
        p1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="P1", parent_task_id=root_id,
        )
        p2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="P2", parent_task_id=root_id,
        )
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Child",
            parent_task_ids=[p1, p2],
        )
        parent_ids = await mailbox_db.get_task_parent_ids(child_id)
        assert parent_ids == [p1, p2]

    @pytest.mark.asyncio
    async def test_single_parent_via_parent_task_ids(self):
        """A single-element parent_task_ids behaves like parent_task_id."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root",
        )
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Child",
            parent_task_ids=[root_id],
        )
        child = await mailbox_db.get_task(child_id)
        assert child["parent_task_id"] == root_id
        assert child["parent_task_ids"] == [root_id]

    @pytest.mark.asyncio
    async def test_tree_includes_parent_task_ids(self):
        """get_tree returns parent_task_ids on each node."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root", subject="Root"
        )
        p1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="P1", parent_task_id=root_id,
        )
        p2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="P2", parent_task_id=root_id,
        )
        child_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Join",
            parent_task_ids=[p1, p2],
        )

        tree = await mailbox_db.get_tree(root_id)
        # Find the join child (it's under p1 since p1 is primary parent)
        p1_node = next(c for c in tree["children"] if c["id"] == p1)
        join_node = next(c for c in p1_node["children"] if c["id"] == child_id)
        assert join_node["parent_task_ids"] == [p1, p2]

    @pytest.mark.asyncio
    async def test_invalid_parent_in_list_rejected(self):
        """A non-existent parent in parent_task_ids raises ValueError."""
        root_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root",
        )
        with pytest.raises(ValueError, match="does not exist"):
            await mailbox_db.insert_task(
                creator="doot", assignee="oppy", prompt="Bad child",
                parent_task_ids=[root_id, 999],
            )


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
    async def test_terminal_state_guard_completed_to_failed(self, client):
        """Cannot change status of a completed task (e.g. runner exit handler)."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Complete the task
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "Done"},
            headers=OPPY_HEADERS,
        )

        # Try to mark failed (simulates runner exit handler)
        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed", "output": "Session exited with code 0"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 409
        assert "terminal state" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_terminal_state_guard_failed_to_completed(self, client):
        """Cannot change status of a failed task."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed"},
            headers=OPPY_HEADERS,
        )

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_terminal_state_allows_output_update(self, client):
        """Non-status updates (output) still work on terminal tasks."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "Done"},
            headers=OPPY_HEADERS,
        )

        # Output-only update should still work
        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"output": "Updated output"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["output"] == "Updated output"

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
# Tasks — API: metadata and depth
# ---------------------------------------------------------------------------


class TestAPIMetadataAndDepth:
    @pytest.mark.asyncio
    async def test_create_task_with_metadata(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Root task",
                "subject": "Root",
                "metadata": {"max_depth": 10},
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        data = resp.json()
        assert data["metadata"] == {"max_depth": 10}
        assert data["depth"] == 0

    @pytest.mark.asyncio
    async def test_depth_increases_with_nesting(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Root", "subject": "Root"},
            headers=DOOT_HEADERS,
        )
        root_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Child", "parent_task_id": root_id},
            headers=DOOT_HEADERS,
        )
        child_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{child_id}", headers=DOOT_HEADERS)
        assert resp.json()["depth"] == 1

    @pytest.mark.asyncio
    async def test_task_list_includes_depth(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Root", "subject": "Root"},
            headers=DOOT_HEADERS,
        )
        root_id = resp.json()["id"]
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Child", "parent_task_id": root_id},
            headers=DOOT_HEADERS,
        )

        resp = await client.get("/api/v1/tasks", headers=DOOT_HEADERS)
        tasks = resp.json()
        depths = {t["subject"]: t["depth"] for t in tasks}
        assert depths.get("Root") == 0

    @pytest.mark.asyncio
    async def test_tree_includes_metadata_and_depth(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Root",
                "subject": "Root",
                "metadata": {"max_depth": 5},
            },
            headers=DOOT_HEADERS,
        )
        root_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Child", "parent_task_id": root_id},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(f"/api/v1/trees/{root_id}", headers=DOOT_HEADERS)
        tree = resp.json()
        assert tree["metadata"] == {"max_depth": 5}
        assert tree["depth"] == 0
        assert tree["children"][0]["depth"] == 1
        assert tree["children"][0]["metadata"] is None


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

    @pytest.mark.asyncio
    @patch("clade.mcp.tools.task_tools.initiate_task")
    async def test_card_id_links_to_card(self, mock_initiate):
        mock_client = AsyncMock()
        mock_client.create_task.return_value = {"id": 11}
        mock_client.update_task.return_value = {"id": 11, "status": "launched"}
        mock_client.add_card_link.return_value = {}
        mock_initiate.return_value = TaskResult(
            success=True,
            session_name="task-oppy-test-card-123",
            host="masuda",
            message="Task launched",
        )
        tools = _make_task_tools(mock_client)
        result = await tools["initiate_ssh_task"](
            "oppy", "Do stuff", subject="Test", card_id=38
        )
        assert "Task #11" in result
        assert "launched successfully" in result
        assert "Linked to card: #38" in result
        mock_client.add_card_link.assert_called_once_with(38, "task", "11")

    @pytest.mark.asyncio
    @patch("clade.mcp.tools.task_tools.initiate_task")
    async def test_no_card_id_no_link(self, mock_initiate):
        mock_client = AsyncMock()
        mock_client.create_task.return_value = {"id": 12}
        mock_client.update_task.return_value = {"id": 12, "status": "launched"}
        mock_initiate.return_value = TaskResult(
            success=True,
            session_name="task-oppy-test-nocard-456",
            host="masuda",
            message="Task launched",
        )
        tools = _make_task_tools(mock_client)
        result = await tools["initiate_ssh_task"]("oppy", "Do stuff", subject="Test")
        assert "Linked to card" not in result
        mock_client.add_card_link.assert_not_called()


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


# ---------------------------------------------------------------------------
# Database — update_task_parent and count_children
# ---------------------------------------------------------------------------


class TestDatabaseUpdateTaskParent:
    @pytest.mark.asyncio
    async def test_update_task_parent(self):
        """Reparent a standalone task under another."""
        a = await mailbox_db.insert_task(creator="doot", assignee="oppy", prompt="A")
        b = await mailbox_db.insert_task(creator="doot", assignee="oppy", prompt="B")

        await mailbox_db.update_task_parent(b, a)

        task_b = await mailbox_db.get_task(b)
        assert task_b["parent_task_id"] == a
        assert task_b["root_task_id"] == a

    @pytest.mark.asyncio
    async def test_update_task_parent_cascades(self):
        """Reparenting a subtree cascades root_task_id to all descendants."""
        # Build tree: A -> B -> C
        a = await mailbox_db.insert_task(creator="doot", assignee="oppy", prompt="A", subject="A")
        b = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="B", parent_task_id=a
        )
        c = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C", parent_task_id=b
        )

        # Create a separate tree: D
        d = await mailbox_db.insert_task(creator="doot", assignee="oppy", prompt="D", subject="D")

        # Reparent B (and its subtree) under D
        await mailbox_db.update_task_parent(b, d)

        task_b = await mailbox_db.get_task(b)
        task_c = await mailbox_db.get_task(c)
        assert task_b["parent_task_id"] == d
        assert task_b["root_task_id"] == d
        assert task_c["root_task_id"] == d  # cascaded

    @pytest.mark.asyncio
    async def test_update_task_parent_invalid(self):
        """Non-existent parent raises ValueError."""
        a = await mailbox_db.insert_task(creator="doot", assignee="oppy", prompt="A")
        with pytest.raises(ValueError, match="does not exist"):
            await mailbox_db.update_task_parent(a, 9999)

    @pytest.mark.asyncio
    async def test_update_task_parent_circular(self):
        """Reparenting A under B when B is already under A raises ValueError."""
        a = await mailbox_db.insert_task(creator="doot", assignee="oppy", prompt="A", subject="A")
        b = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="B", parent_task_id=a
        )
        with pytest.raises(ValueError, match="cycle"):
            await mailbox_db.update_task_parent(a, b)


class TestDatabaseCountChildren:
    @pytest.mark.asyncio
    async def test_count_children(self):
        parent = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Parent"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C1", parent_task_id=parent
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="C2", parent_task_id=parent
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="C3", parent_task_id=parent
        )

        count = await mailbox_db.count_children(parent)
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_children_none(self):
        task = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Leaf"
        )
        count = await mailbox_db.count_children(task)
        assert count == 0


# ---------------------------------------------------------------------------
# Retry task — API endpoint
# ---------------------------------------------------------------------------


class TestAPIRetryTask:
    @pytest.mark.asyncio
    async def test_retry_failed_task(self, client):
        """Retry a failed task — child created with correct parent/root/subject."""
        # Create and fail a task
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Original job"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed", "output": "Something broke"},
            headers=OPPY_HEADERS,
        )

        # Register an Ember URL and API key so the retry can find them
        await mailbox_db.upsert_ember("oppy", "http://fake-ember:8100")
        await mailbox_db.insert_api_key("oppy", "oppy-ember-key")

        # Mock the Ember HTTP call
        with patch("hearth.app.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"status": "accepted"}
            mock_instance.post.return_value = mock_resp
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            resp = await client.post(
                f"/api/v1/tasks/{task_id}/retry",
                headers=DOOT_HEADERS,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["parent_task_id"] == task_id
        assert data["root_task_id"] == task_id
        assert data["subject"] == "Retry #1: Original job"
        assert data["status"] == "launched"
        assert data["assignee"] == "oppy"
        assert data["prompt"] == "Do stuff"

    @pytest.mark.asyncio
    async def test_retry_non_failed_409(self, client):
        """Cannot retry a task that isn't failed."""
        for status in ["pending", "completed", "killed"]:
            resp = await client.post(
                "/api/v1/tasks",
                json={"assignee": "oppy", "prompt": "Test"},
                headers=DOOT_HEADERS,
            )
            task_id = resp.json()["id"]
            if status != "pending":
                await client.patch(
                    f"/api/v1/tasks/{task_id}",
                    json={"status": status},
                    headers=OPPY_HEADERS,
                )

            resp = await client.post(
                f"/api/v1/tasks/{task_id}/retry",
                headers=DOOT_HEADERS,
            )
            assert resp.status_code == 409, f"Expected 409 for status={status}"

    @pytest.mark.asyncio
    async def test_retry_numbering(self, client):
        """Two retries produce Retry #1 and Retry #2."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "The job"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed"},
            headers=OPPY_HEADERS,
        )

        await mailbox_db.upsert_ember("oppy", "http://fake-ember:8100")
        await mailbox_db.insert_api_key("oppy", "oppy-ember-key")

        subjects = []
        for _ in range(2):
            # Re-fail the original (retry only works on failed tasks)
            # Actually we retry the same failed task twice
            with patch("hearth.app.httpx.AsyncClient") as MockClient:
                mock_instance = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status.return_value = None
                mock_resp.json.return_value = {"status": "accepted"}
                mock_instance.post.return_value = mock_resp
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_instance

                resp = await client.post(
                    f"/api/v1/tasks/{task_id}/retry",
                    headers=DOOT_HEADERS,
                )
                assert resp.status_code == 200
                subjects.append(resp.json()["subject"])

        assert subjects[0] == "Retry #1: The job"
        assert subjects[1] == "Retry #2: The job"

    @pytest.mark.asyncio
    async def test_retry_no_ember_422(self, client):
        """No Ember configured — child task created but marked failed, returns 422."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Job"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed"},
            headers=OPPY_HEADERS,
        )

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/retry",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422
        assert "No Ember URL" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_retry_not_found(self, client):
        resp = await client.post(
            "/api/v1/tasks/9999/retry",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_forbidden(self, client):
        """Only assignee, creator, or admin can retry."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed"},
            headers=OPPY_HEADERS,
        )

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/retry",
            headers=JERRY_HEADERS,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_retry_inherits_working_dir_and_project(self, client):
        """Retry inherits working_dir and project from the original task."""
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Do stuff",
                "subject": "Job with wd",
                "working_dir": "/home/ian/.local/share/clade",
                "project": "clade",
            },
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed", "output": "broke"},
            headers=OPPY_HEADERS,
        )

        await mailbox_db.upsert_ember("oppy", "http://fake-ember:8100")
        await mailbox_db.insert_api_key("oppy", "oppy-ember-key")

        with patch("hearth.app.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"status": "accepted"}
            mock_instance.post.return_value = mock_resp
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            resp = await client.post(
                f"/api/v1/tasks/{task_id}/retry",
                headers=DOOT_HEADERS,
            )

            # Verify the Ember was called with the correct working_dir
            call_args = mock_instance.post.call_args
            ember_payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert ember_payload["working_dir"] == "/home/ian/.local/share/clade"

        assert resp.status_code == 200
        child = resp.json()
        assert child["working_dir"] == "/home/ian/.local/share/clade"
        assert child["project"] == "clade"


# ---------------------------------------------------------------------------
# PATCH parent_task_id — API endpoint
# ---------------------------------------------------------------------------


class TestAPIPatchParentTaskId:
    @pytest.mark.asyncio
    async def test_patch_parent_task_id(self, client):
        """Reparent a standalone task via PATCH."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Parent", "subject": "Parent"},
            headers=DOOT_HEADERS,
        )
        parent_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Child", "subject": "Child"},
            headers=DOOT_HEADERS,
        )
        child_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{child_id}",
            json={"parent_task_id": parent_id},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent_task_id"] == parent_id
        assert data["root_task_id"] == parent_id

    @pytest.mark.asyncio
    async def test_patch_parent_cascade(self, client):
        """Reparenting a subtree cascades root_task_id to descendants."""
        # Build tree: A -> B -> C
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "A", "subject": "A"},
            headers=DOOT_HEADERS,
        )
        a_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "B", "parent_task_id": a_id},
            headers=DOOT_HEADERS,
        )
        b_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "C", "parent_task_id": b_id},
            headers=DOOT_HEADERS,
        )
        c_id = resp.json()["id"]

        # Create D
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "D", "subject": "D"},
            headers=DOOT_HEADERS,
        )
        d_id = resp.json()["id"]

        # Reparent B under D
        resp = await client.patch(
            f"/api/v1/tasks/{b_id}",
            json={"parent_task_id": d_id},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["root_task_id"] == d_id

        # Verify C's root also cascaded
        resp = await client.get(f"/api/v1/tasks/{c_id}", headers=DOOT_HEADERS)
        assert resp.json()["root_task_id"] == d_id

    @pytest.mark.asyncio
    async def test_patch_parent_invalid_422(self, client):
        """Non-existent parent returns 422."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Task"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"parent_task_id": 9999},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_parent_and_status(self, client):
        """Both parent_task_id and status in same request."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Parent", "subject": "Parent"},
            headers=DOOT_HEADERS,
        )
        parent_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Child"},
            headers=DOOT_HEADERS,
        )
        child_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{child_id}",
            json={"parent_task_id": parent_id, "status": "in_progress"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent_task_id"] == parent_id
        assert data["status"] == "in_progress"


# ---------------------------------------------------------------------------
# MailboxClient — retry_task and update_task with parent_task_id
# ---------------------------------------------------------------------------


class TestMailboxClientRetryTask:
    def setup_method(self):
        self.client = MailboxClient("http://localhost:8000", "test-key")

    def _make_mock_resp(self, json_data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def _make_async_client(self, post_resp=None, patch_resp=None):
        instance = AsyncMock()
        if post_resp is not None:
            instance.post.return_value = post_resp
        if patch_resp is not None:
            instance.patch.return_value = patch_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        return instance

    @pytest.mark.asyncio
    async def test_retry_task_client(self):
        mock_resp = self._make_mock_resp({
            "id": 10, "creator": "doot", "assignee": "oppy",
            "subject": "Retry #1: Original", "status": "launched",
            "prompt": "Do stuff", "parent_task_id": 5, "root_task_id": 5,
            "created_at": "2026-02-21T10:00:00Z",
            "started_at": None, "completed_at": None,
        })
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.retry_task(5)
            assert result["id"] == 10
            assert result["status"] == "launched"
            instance.post.assert_called_once()
            call_args = instance.post.call_args
            assert "/tasks/5/retry" in str(call_args)

    @pytest.mark.asyncio
    async def test_update_task_with_parent(self):
        mock_resp = self._make_mock_resp({
            "id": 2, "creator": "doot", "assignee": "oppy", "subject": "Task",
            "prompt": "Do stuff", "status": "pending",
            "created_at": "2026-02-21T10:00:00Z",
            "started_at": None, "completed_at": None,
            "parent_task_id": 1, "root_task_id": 1,
        })
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(patch_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.update_task(2, parent_task_id=1)
            assert result["parent_task_id"] == 1
            call_kwargs = instance.patch.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["parent_task_id"] == 1


# ---------------------------------------------------------------------------
# MCP tools — retry_task and update_task with parent_task_id
# ---------------------------------------------------------------------------


class TestRetryTaskTool:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_mailbox_tools(None)
        result = await tools["retry_task"](1)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        mock_client = AsyncMock()
        mock_client.retry_task.return_value = {
            "id": 10, "subject": "Retry #1: Job", "status": "launched",
            "assignee": "oppy", "parent_task_id": 5,
        }
        tools = _make_mailbox_tools(mock_client)
        result = await tools["retry_task"](5)
        assert "Retry task #10 created" in result
        assert "Retry #1: Job" in result
        assert "launched" in result
        assert "oppy" in result

    @pytest.mark.asyncio
    async def test_error(self):
        mock_client = AsyncMock()
        mock_client.retry_task.side_effect = Exception("409: Cannot retry")
        tools = _make_mailbox_tools(mock_client)
        result = await tools["retry_task"](1)
        assert "Error" in result


class TestUpdateTaskParentTool:
    @pytest.mark.asyncio
    async def test_update_task_with_parent(self):
        mock_client = AsyncMock()
        mock_client.update_task.return_value = {
            "id": 2, "status": "pending", "assignee": "oppy",
            "parent_task_id": 1, "root_task_id": 1,
        }
        tools = _make_mailbox_tools(mock_client)
        result = await tools["update_task"](2, parent_task_id=1)
        assert "Task #2 updated" in result
        assert "Parent: #1" in result
        assert "Root: #1" in result
        mock_client.update_task.assert_called_once_with(
            2, status=None, output=None, parent_task_id=1
        )


# ---------------------------------------------------------------------------
# on_complete field
# ---------------------------------------------------------------------------


class TestOnCompleteDB:
    @pytest.mark.asyncio
    async def test_insert_task_with_on_complete(self):
        task_id = await mailbox_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="Do work",
            subject="Test task",
            on_complete="Deploy to production after completion",
        )
        task = await mailbox_db.get_task(task_id)
        assert task["on_complete"] == "Deploy to production after completion"

    @pytest.mark.asyncio
    async def test_insert_task_without_on_complete(self):
        task_id = await mailbox_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="Do work",
        )
        task = await mailbox_db.get_task(task_id)
        assert task["on_complete"] is None

    @pytest.mark.asyncio
    async def test_on_complete_in_tree(self):
        root_id = await mailbox_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="Root task",
            on_complete="Run tests when done",
        )
        tree = await mailbox_db.get_tree(root_id)
        assert tree["on_complete"] == "Run tests when done"


class TestOnCompleteAPI:
    @pytest.mark.asyncio
    async def test_create_task_with_on_complete(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Do the thing",
                "subject": "Test",
                "on_complete": "Notify Ian when done",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        detail = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        assert detail.status_code == 200
        assert detail.json()["on_complete"] == "Notify Ian when done"

    @pytest.mark.asyncio
    async def test_create_task_without_on_complete(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do work"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        detail = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        assert detail.json()["on_complete"] is None

    @pytest.mark.asyncio
    async def test_on_complete_in_tree_api(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Root",
                "on_complete": "Follow up instructions",
            },
            headers=DOOT_HEADERS,
        )
        root_id = resp.json()["id"]
        tree_resp = await client.get(f"/api/v1/trees/{root_id}", headers=DOOT_HEADERS)
        assert tree_resp.status_code == 200
        assert tree_resp.json()["on_complete"] == "Follow up instructions"


# ---------------------------------------------------------------------------
# Auto-sync card status from linked tasks
# ---------------------------------------------------------------------------


class TestAutoSyncCardStatus:
    @pytest.mark.asyncio
    async def test_task_in_progress_syncs_linked_card(self, client):
        """When a task moves to in_progress, linked cards in backlog/todo move to in_progress."""
        # Create a task
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Create a card linked to the task
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Feature card",
                "col": "todo",
                "links": [{"object_type": "task", "object_id": str(task_id)}],
            },
            headers=DOOT_HEADERS,
        )
        card_id = resp.json()["id"]
        assert resp.json()["col"] == "todo"

        # Move task to in_progress
        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200

        # Card should now be in_progress with assignee set
        resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "in_progress"
        assert resp.json()["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_task_in_progress_syncs_backlog_card(self, client):
        """Cards in backlog also sync forward to in_progress."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "GPU job"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Backlog card",
                "col": "backlog",
                "links": [{"object_type": "task", "object_id": str(task_id)}],
            },
            headers=DOOT_HEADERS,
        )
        card_id = resp.json()["id"]

        # Move task to in_progress
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=JERRY_HEADERS,
        )

        resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "in_progress"
        assert resp.json()["assignee"] == "jerry"

    @pytest.mark.asyncio
    async def test_done_card_reopens_on_in_progress(self, client):
        """Cards in done should be re-opened to in_progress when a linked task becomes active."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Done card",
                "col": "done",
                "links": [{"object_type": "task", "object_id": str(task_id)}],
            },
            headers=DOOT_HEADERS,
        )
        card_id = resp.json()["id"]

        # Move task to in_progress
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )

        # Card should be re-opened to in_progress
        resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_no_sync_when_card_archived(self, client):
        """Cards in archived column should NOT be moved when a linked task moves to in_progress."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Archived card",
                "col": "archived",
                "links": [{"object_type": "task", "object_id": str(task_id)}],
            },
            headers=DOOT_HEADERS,
        )
        card_id = resp.json()["id"]

        # Move task to in_progress
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )

        # Card should still be archived
        resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "archived"

    @pytest.mark.asyncio
    async def test_no_sync_when_card_already_in_progress(self, client):
        """Cards already in_progress should not be touched (preserves existing assignee)."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Active card",
                "col": "in_progress",
                "assignee": "jerry",
                "links": [{"object_type": "task", "object_id": str(task_id)}],
            },
            headers=DOOT_HEADERS,
        )
        card_id = resp.json()["id"]

        # Move task to in_progress
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )

        # Card should still have jerry as assignee
        resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "in_progress"
        assert resp.json()["assignee"] == "jerry"

    @pytest.mark.asyncio
    async def test_completed_task_moves_card_to_done(self, client):
        """When a task completes and all linked tasks are terminal, card moves to done."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Todo card",
                "col": "todo",
                "links": [{"object_type": "task", "object_id": str(task_id)}],
            },
            headers=DOOT_HEADERS,
        )
        card_id = resp.json()["id"]

        # Move task directly to completed (skip in_progress)
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=OPPY_HEADERS,
        )

        # Card should move to done (single task completed = all terminal + has completed)
        resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "done"

    @pytest.mark.asyncio
    async def test_no_linked_cards_no_error(self, client):
        """Task with no linked cards should update fine without errors."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
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

    @pytest.mark.asyncio
    async def test_multiple_linked_cards(self, client):
        """Multiple cards linked to the same task all get synced."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        card_ids = []
        for title, col in [("Card A", "backlog"), ("Card B", "todo"), ("Card C", "done")]:
            resp = await client.post(
                "/api/v1/kanban/cards",
                json={
                    "title": title,
                    "col": col,
                    "links": [{"object_type": "task", "object_id": str(task_id)}],
                },
                headers=DOOT_HEADERS,
            )
            card_ids.append(resp.json()["id"])

        # Move task to in_progress
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )

        # Card A (was backlog) -> in_progress
        resp = await client.get(f"/api/v1/kanban/cards/{card_ids[0]}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "in_progress"

        # Card B (was todo) -> in_progress
        resp = await client.get(f"/api/v1/kanban/cards/{card_ids[1]}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "in_progress"

        # Card C (was done) -> re-opened to in_progress (bidirectional sync)
        resp = await client.get(f"/api/v1/kanban/cards/{card_ids[2]}", headers=DOOT_HEADERS)
        assert resp.json()["col"] == "in_progress"


# ---------------------------------------------------------------------------
# Deferred tasks / blocked_by_task_id
# ---------------------------------------------------------------------------


class TestDatabaseBlockedBy:
    @pytest.mark.asyncio
    async def test_insert_task_with_blocked_by(self):
        """A task can be created with blocked_by_task_id."""
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocking task"
        )
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Deferred task",
            blocked_by_task_id=blocker_id,
        )
        task = await mailbox_db.get_task(blocked_id)
        assert task["blocked_by_task_id"] == blocker_id
        assert task["status"] == "pending"
        # Auto-defaults parent_task_id to blocker when not explicitly set
        assert task["parent_task_id"] == blocker_id

    @pytest.mark.asyncio
    async def test_blocked_by_auto_parents_to_blocker(self):
        """blocked_by_task_id auto-sets parent_task_id when not explicitly provided."""
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Step 1"
        )
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Step 2",
            blocked_by_task_id=blocker_id,
        )
        task = await mailbox_db.get_task(blocked_id)
        assert task["parent_task_id"] == blocker_id
        assert task["root_task_id"] == blocker_id

    @pytest.mark.asyncio
    async def test_blocked_by_explicit_parent_overrides(self):
        """Explicit parent_task_id is not overridden by blocked_by_task_id."""
        grandparent_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Root task"
        )
        sibling_a_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Sibling A",
            parent_task_id=grandparent_id,
        )
        sibling_b_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Sibling B",
            parent_task_id=grandparent_id,
            blocked_by_task_id=sibling_a_id,
        )
        task = await mailbox_db.get_task(sibling_b_id)
        assert task["parent_task_id"] == grandparent_id  # explicit parent wins
        assert task["blocked_by_task_id"] == sibling_a_id
        assert task["root_task_id"] == grandparent_id

    @pytest.mark.asyncio
    async def test_blocked_by_nonexistent_task_raises(self):
        """blocked_by_task_id must reference an existing task."""
        with pytest.raises(ValueError, match="does not exist"):
            await mailbox_db.insert_task(
                creator="doot", assignee="oppy", prompt="Bad",
                blocked_by_task_id=9999,
            )

    @pytest.mark.asyncio
    async def test_blocked_by_completed_task_clears(self):
        """If the blocking task is already completed, blocked_by is cleared."""
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Already done"
        )
        await mailbox_db.update_task(blocker_id, status="completed")
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Should not be blocked",
            blocked_by_task_id=blocker_id,
        )
        task = await mailbox_db.get_task(blocked_id)
        assert task["blocked_by_task_id"] is None

    @pytest.mark.asyncio
    async def test_get_tasks_blocked_by(self):
        """get_tasks_blocked_by returns pending tasks blocked by a given task."""
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocking task"
        )
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Deferred task",
            blocked_by_task_id=blocker_id,
        )
        # Also add a non-blocked task — should not appear
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Normal task"
        )

        blocked = await mailbox_db.get_tasks_blocked_by(blocker_id)
        assert len(blocked) == 1
        assert blocked[0]["id"] == blocked_id

    @pytest.mark.asyncio
    async def test_clear_blocked_by(self):
        """clear_blocked_by removes the blocked_by reference."""
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocker"
        )
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocked",
            blocked_by_task_id=blocker_id,
        )
        await mailbox_db.clear_blocked_by(blocked_id)
        task = await mailbox_db.get_task(blocked_id)
        assert task["blocked_by_task_id"] is None

    @pytest.mark.asyncio
    async def test_get_task_includes_blocked_tasks(self):
        """get_task detail includes blocked_tasks list."""
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocker"
        )
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocked",
            blocked_by_task_id=blocker_id,
        )
        task = await mailbox_db.get_task(blocker_id)
        assert len(task["blocked_tasks"]) == 1
        assert task["blocked_tasks"][0]["id"] == blocked_id

    @pytest.mark.asyncio
    async def test_get_tasks_includes_blocked_by_field(self):
        """get_tasks list includes blocked_by_task_id."""
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocker"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocked",
            blocked_by_task_id=blocker_id,
        )
        tasks = await mailbox_db.get_tasks()
        blocked_tasks = [t for t in tasks if t.get("blocked_by_task_id")]
        assert len(blocked_tasks) == 1
        assert blocked_tasks[0]["blocked_by_task_id"] == blocker_id


class TestAPIBlockedBy:
    @pytest.mark.asyncio
    async def test_create_task_with_blocked_by(self, client):
        """POST /tasks with blocked_by_task_id creates a deferred task."""
        # Create blocker
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Blocker", "subject": "Blocker"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        blocker_id = resp.json()["id"]

        # Create blocked task
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Deferred work",
                "subject": "Deferred",
                "blocked_by_task_id": blocker_id,
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        blocked_id = resp.json()["id"]

        # Verify via GET
        resp = await client.get(f"/api/v1/tasks/{blocked_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked_by_task_id"] == blocker_id
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_task_blocked_by_nonexistent_returns_422(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Bad",
                "blocked_by_task_id": 9999,
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_task_detail_shows_blocked_tasks(self, client):
        """GET /tasks/{id} includes blocked_tasks when tasks are waiting."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Blocker"},
            headers=DOOT_HEADERS,
        )
        blocker_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Blocked",
                "blocked_by_task_id": blocker_id,
            },
            headers=DOOT_HEADERS,
        )
        blocked_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{blocker_id}", headers=DOOT_HEADERS)
        data = resp.json()
        assert len(data["blocked_tasks"]) == 1
        assert data["blocked_tasks"][0]["id"] == blocked_id

    @pytest.mark.asyncio
    async def test_task_list_shows_blocked_by(self, client):
        """GET /tasks includes blocked_by_task_id in summary."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Blocker"},
            headers=DOOT_HEADERS,
        )
        blocker_id = resp.json()["id"]

        await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Blocked",
                "blocked_by_task_id": blocker_id,
            },
            headers=DOOT_HEADERS,
        )

        resp = await client.get("/api/v1/tasks", headers=DOOT_HEADERS)
        tasks = resp.json()
        blocked = [t for t in tasks if t.get("blocked_by_task_id")]
        assert len(blocked) == 1
        assert blocked[0]["blocked_by_task_id"] == blocker_id

    @pytest.mark.asyncio
    async def test_tree_summary_includes_blocked_count(self, client):
        """GET /trees includes blocked count for deferred tasks."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Root", "subject": "Root"},
            headers=DOOT_HEADERS,
        )
        root_id = resp.json()["id"]

        # Create a child that's blocked by the root
        await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Blocked child",
                "parent_task_id": root_id,
                "blocked_by_task_id": root_id,
            },
            headers=DOOT_HEADERS,
        )

        resp = await client.get("/api/v1/trees", headers=DOOT_HEADERS)
        trees = resp.json()
        tree = next(t for t in trees if t["root_task_id"] == root_id)
        assert tree["blocked"] == 1
        # The root itself is pending but not blocked
        assert tree["pending"] == 1


class TestUnblockOnCompletion:
    @pytest.mark.asyncio
    @patch("hearth.app._maybe_trigger_conductor_tick")
    async def test_completing_blocker_clears_blocked_by(self, mock_tick, client):
        """When a blocking task completes, blocked tasks get unblocked and delegated."""
        # Create blocker
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Blocker", "subject": "Blocker"},
            headers=DOOT_HEADERS,
        )
        blocker_id = resp.json()["id"]

        # Create blocked task
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Deferred work",
                "subject": "Deferred",
                "blocked_by_task_id": blocker_id,
            },
            headers=DOOT_HEADERS,
        )
        blocked_id = resp.json()["id"]

        # Complete the blocker (mock Ember so delegation doesn't fail on missing URL)
        with patch("hearth.app._unblock_and_delegate") as mock_unblock:
            mock_unblock.return_value = None  # Skip actual Ember delegation
            resp = await client.patch(
                f"/api/v1/tasks/{blocker_id}",
                json={"status": "completed"},
                headers=DOOT_HEADERS,
            )
            assert resp.status_code == 200
            mock_unblock.assert_called_once_with(blocker_id)

    @pytest.mark.asyncio
    @patch("hearth.app._maybe_trigger_conductor_tick")
    async def test_unblock_and_delegate_clears_blocked_by(self, mock_tick, client):
        """_unblock_and_delegate clears blocked_by_task_id."""
        from hearth.app import _unblock_and_delegate

        # Create blocker
        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocker"
        )
        # Create blocked task
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocked",
            blocked_by_task_id=blocker_id,
        )

        # Call _unblock_and_delegate — Ember not configured, so delegation will fail
        # but blocked_by should still be cleared
        await _unblock_and_delegate(blocker_id)

        task = await mailbox_db.get_task(blocked_id)
        assert task["blocked_by_task_id"] is None


# ---------------------------------------------------------------------------
# Cascade failure tests
# ---------------------------------------------------------------------------


class TestCascadeFailure:
    """Tests for cascading failure to downstream blocked tasks."""

    @pytest.mark.asyncio
    async def test_cascade_failure_single_level(self):
        """Failing a task cascades failure to pending tasks blocked by it."""
        from hearth.app import _cascade_failure

        blocker_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocker"
        )
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocked",
            blocked_by_task_id=blocker_id,
        )

        await _cascade_failure(blocker_id)

        task = await mailbox_db.get_task(blocked_id)
        assert task["status"] == "failed"
        assert task["blocked_by_task_id"] is None
        assert f"Upstream task #{blocker_id} failed" in task["output"]
        assert task["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_cascade_failure_recursive(self):
        """Cascade propagates through multiple levels: A -> B -> C."""
        from hearth.app import _cascade_failure

        a = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task A"
        )
        b = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task B",
            blocked_by_task_id=a,
        )
        c = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task C",
            blocked_by_task_id=b,
        )

        await _cascade_failure(a)

        task_b = await mailbox_db.get_task(b)
        assert task_b["status"] == "failed"
        assert f"Upstream task #{a} failed" in task_b["output"]

        task_c = await mailbox_db.get_task(c)
        assert task_c["status"] == "failed"
        assert f"Upstream task #{b} failed" in task_c["output"]

    @pytest.mark.asyncio
    async def test_cascade_failure_multiple_blocked(self):
        """Multiple tasks blocked by the same task all get failed."""
        from hearth.app import _cascade_failure

        blocker = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocker"
        )
        b1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocked 1",
            blocked_by_task_id=blocker,
        )
        b2 = await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Blocked 2",
            blocked_by_task_id=blocker,
        )

        await _cascade_failure(blocker)

        for tid in (b1, b2):
            task = await mailbox_db.get_task(tid)
            assert task["status"] == "failed"
            assert task["blocked_by_task_id"] is None

    @pytest.mark.asyncio
    async def test_cascade_failure_skips_non_pending(self):
        """Only pending tasks are cascade-failed; in_progress tasks are untouched."""
        from hearth.app import _cascade_failure

        blocker = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocker"
        )
        blocked_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Blocked",
            blocked_by_task_id=blocker,
        )
        # Manually move to in_progress (simulating it was already picked up)
        await mailbox_db.update_task(blocked_id, status="in_progress")

        await _cascade_failure(blocker)

        task = await mailbox_db.get_task(blocked_id)
        # Should still be in_progress, not failed
        assert task["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_cascade_failure_no_blocked_tasks(self):
        """Cascade on a task with no blocked dependents is a no-op."""
        from hearth.app import _cascade_failure

        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Standalone"
        )
        # Should not raise
        await _cascade_failure(task_id)

    @pytest.mark.asyncio
    @patch("hearth.app._maybe_trigger_conductor_tick")
    async def test_cascade_failure_via_api(self, mock_tick, client):
        """Failing a task via the API cascades failure to blocked tasks."""
        # Create blocker
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Blocker", "subject": "Blocker"},
            headers=DOOT_HEADERS,
        )
        blocker_id = resp.json()["id"]

        # Create blocked task
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Blocked",
                "subject": "Blocked",
                "blocked_by_task_id": blocker_id,
            },
            headers=DOOT_HEADERS,
        )
        blocked_id = resp.json()["id"]

        # Fail the blocker via API
        resp = await client.patch(
            f"/api/v1/tasks/{blocker_id}",
            json={"status": "failed", "output": "Something went wrong"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200

        # Verify downstream task was cascade-failed
        resp = await client.get(
            f"/api/v1/tasks/{blocked_id}", headers=DOOT_HEADERS
        )
        data = resp.json()
        assert data["status"] == "failed"
        assert f"Upstream task #{blocker_id} failed" in data["output"]

    @pytest.mark.asyncio
    @patch("hearth.app._maybe_trigger_conductor_tick")
    async def test_cascade_failure_recursive_via_api(self, mock_tick, client):
        """Recursive cascade works through the API: A -> B -> C all fail."""
        # A
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "A", "subject": "A"},
            headers=DOOT_HEADERS,
        )
        a_id = resp.json()["id"]

        # B blocked by A
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "B", "subject": "B", "blocked_by_task_id": a_id},
            headers=DOOT_HEADERS,
        )
        b_id = resp.json()["id"]

        # C blocked by B
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "C", "subject": "C", "blocked_by_task_id": b_id},
            headers=DOOT_HEADERS,
        )
        c_id = resp.json()["id"]

        # Fail A
        resp = await client.patch(
            f"/api/v1/tasks/{a_id}",
            json={"status": "failed"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200

        # B and C should both be failed
        for tid, upstream in [(b_id, a_id), (c_id, b_id)]:
            resp = await client.get(f"/api/v1/tasks/{tid}", headers=DOOT_HEADERS)
            data = resp.json()
            assert data["status"] == "failed"
            assert f"Upstream task #{upstream} failed" in data["output"]
