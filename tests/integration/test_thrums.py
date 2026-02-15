"""Tests for the thrum system: database, API, client, and MCP tools."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

os.environ["MAILBOX_API_KEYS"] = "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian"

# Force-reload API_KEYS since hearth.config may have been imported with fewer keys
from hearth import config as hearth_config
hearth_config.API_KEYS = hearth_config.parse_api_keys(os.environ["MAILBOX_API_KEYS"])

from httpx import ASGITransport, AsyncClient

from hearth.app import app
from hearth import db as hearth_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}
JERRY_HEADERS = {"Authorization": "Bearer test-key-jerry"}
KAMAJI_HEADERS = {"Authorization": "Bearer test-key-kamaji"}
IAN_HEADERS = {"Authorization": "Bearer test-key-ian"}


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Use a fresh SQLite database for each test."""
    db_path = str(tmp_path / "test.db")
    original = hearth_db.DB_PATH
    hearth_db.DB_PATH = db_path
    await hearth_db.init_db()
    yield db_path
    hearth_db.DB_PATH = original


@pytest_asyncio.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Thrums — database layer
# ---------------------------------------------------------------------------


class TestDatabaseThrums:
    @pytest.mark.asyncio
    async def test_insert_and_get_thrum(self):
        thrum_id = await hearth_db.insert_thrum(
            creator="kamaji",
            title="Run experiments",
            goal="Train model on new dataset",
            plan="Step 1: preprocess\nStep 2: train",
            priority="high",
        )
        assert thrum_id > 0

        thrum = await hearth_db.get_thrum(thrum_id)
        assert thrum is not None
        assert thrum["creator"] == "kamaji"
        assert thrum["title"] == "Run experiments"
        assert thrum["goal"] == "Train model on new dataset"
        assert thrum["plan"] == "Step 1: preprocess\nStep 2: train"
        assert thrum["status"] == "pending"
        assert thrum["priority"] == "high"
        assert thrum["tasks"] == []

    @pytest.mark.asyncio
    async def test_get_thrum_not_found(self):
        thrum = await hearth_db.get_thrum(999)
        assert thrum is None

    @pytest.mark.asyncio
    async def test_get_thrums_all(self):
        await hearth_db.insert_thrum(creator="kamaji", title="Thrum 1")
        await hearth_db.insert_thrum(creator="kamaji", title="Thrum 2")
        thrums = await hearth_db.get_thrums()
        assert len(thrums) == 2

    @pytest.mark.asyncio
    async def test_get_thrums_filter_status(self):
        t1 = await hearth_db.insert_thrum(creator="kamaji", title="Thrum 1")
        await hearth_db.insert_thrum(creator="kamaji", title="Thrum 2")
        await hearth_db.update_thrum(t1, status="active")
        thrums = await hearth_db.get_thrums(status="pending")
        assert len(thrums) == 1
        assert thrums[0]["title"] == "Thrum 2"

    @pytest.mark.asyncio
    async def test_get_thrums_filter_creator(self):
        await hearth_db.insert_thrum(creator="kamaji", title="Thrum 1")
        await hearth_db.insert_thrum(creator="doot", title="Thrum 2")
        thrums = await hearth_db.get_thrums(creator="doot")
        assert len(thrums) == 1
        assert thrums[0]["creator"] == "doot"

    @pytest.mark.asyncio
    async def test_get_thrums_limit(self):
        for i in range(5):
            await hearth_db.insert_thrum(creator="kamaji", title=f"Thrum {i}")
        thrums = await hearth_db.get_thrums(limit=3)
        assert len(thrums) == 3

    @pytest.mark.asyncio
    async def test_update_thrum_status(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        updated = await hearth_db.update_thrum(thrum_id, status="active")
        assert updated is not None
        assert updated["status"] == "active"

    @pytest.mark.asyncio
    async def test_update_thrum_plan(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        updated = await hearth_db.update_thrum(thrum_id, plan="Do this then that")
        assert updated["plan"] == "Do this then that"

    @pytest.mark.asyncio
    async def test_update_thrum_output(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        updated = await hearth_db.update_thrum(
            thrum_id, status="completed", output="All done"
        )
        assert updated["status"] == "completed"
        assert updated["output"] == "All done"

    @pytest.mark.asyncio
    async def test_update_thrum_not_found(self):
        result = await hearth_db.update_thrum(999, status="active")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_thrum(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        deleted = await hearth_db.delete_thrum(thrum_id)
        assert deleted is True
        thrum = await hearth_db.get_thrum(thrum_id)
        assert thrum is None

    @pytest.mark.asyncio
    async def test_delete_thrum_not_found(self):
        deleted = await hearth_db.delete_thrum(999)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_thrum_unlinks_tasks(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        task_id = await hearth_db.insert_task(
            creator="kamaji", assignee="oppy", prompt="Do stuff", thrum_id=thrum_id
        )
        await hearth_db.delete_thrum(thrum_id)
        task = await hearth_db.get_task(task_id)
        assert task["thrum_id"] is None


class TestDatabaseThrumTaskLinking:
    @pytest.mark.asyncio
    async def test_task_with_thrum_id(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        task_id = await hearth_db.insert_task(
            creator="kamaji", assignee="oppy", prompt="Do stuff", thrum_id=thrum_id
        )
        thrum = await hearth_db.get_thrum(thrum_id)
        assert len(thrum["tasks"]) == 1
        assert thrum["tasks"][0]["id"] == task_id

    @pytest.mark.asyncio
    async def test_multiple_linked_tasks(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        await hearth_db.insert_task(
            creator="kamaji", assignee="oppy", prompt="Task 1", thrum_id=thrum_id
        )
        await hearth_db.insert_task(
            creator="kamaji", assignee="jerry", prompt="Task 2", thrum_id=thrum_id
        )
        thrum = await hearth_db.get_thrum(thrum_id)
        assert len(thrum["tasks"]) == 2

    @pytest.mark.asyncio
    async def test_task_without_thrum_id(self):
        task_id = await hearth_db.insert_task(
            creator="doot", assignee="oppy", prompt="Standalone"
        )
        task = await hearth_db.get_task(task_id)
        assert task["thrum_id"] is None

    @pytest.mark.asyncio
    async def test_thrum_id_in_task_list(self):
        thrum_id = await hearth_db.insert_thrum(creator="kamaji", title="Test")
        await hearth_db.insert_task(
            creator="kamaji", assignee="oppy", prompt="Task 1", thrum_id=thrum_id
        )
        tasks = await hearth_db.get_tasks()
        assert len(tasks) == 1
        assert tasks[0]["thrum_id"] == thrum_id


# ---------------------------------------------------------------------------
# Thrums — API endpoints
# ---------------------------------------------------------------------------


class TestAPIThrums:
    @pytest.mark.asyncio
    async def test_create_thrum(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={
                "title": "Run experiments",
                "goal": "Train new model",
                "priority": "high",
            },
            headers=KAMAJI_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["message"] == "Thrum created"

    @pytest.mark.asyncio
    async def test_list_thrums(self, client):
        await client.post(
            "/api/v1/thrums",
            json={"title": "Thrum 1"},
            headers=KAMAJI_HEADERS,
        )
        await client.post(
            "/api/v1/thrums",
            json={"title": "Thrum 2"},
            headers=KAMAJI_HEADERS,
        )
        resp = await client.get("/api/v1/thrums", headers=KAMAJI_HEADERS)
        assert resp.status_code == 200
        thrums = resp.json()
        assert len(thrums) == 2

    @pytest.mark.asyncio
    async def test_list_thrums_filter_status(self, client):
        resp1 = await client.post(
            "/api/v1/thrums",
            json={"title": "Thrum 1"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp1.json()["id"]
        await client.post(
            "/api/v1/thrums",
            json={"title": "Thrum 2"},
            headers=KAMAJI_HEADERS,
        )
        await client.patch(
            f"/api/v1/thrums/{thrum_id}",
            json={"status": "active"},
            headers=KAMAJI_HEADERS,
        )
        resp = await client.get(
            "/api/v1/thrums", params={"status": "pending"}, headers=KAMAJI_HEADERS
        )
        thrums = resp.json()
        assert len(thrums) == 1

    @pytest.mark.asyncio
    async def test_get_thrum_detail(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={
                "title": "Test thrum",
                "goal": "Test it",
                "plan": "Step 1: test",
                "priority": "high",
            },
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/thrums/{thrum_id}", headers=KAMAJI_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["creator"] == "kamaji"
        assert data["title"] == "Test thrum"
        assert data["plan"] == "Step 1: test"
        assert data["tasks"] == []

    @pytest.mark.asyncio
    async def test_get_thrum_not_found(self, client):
        resp = await client.get("/api/v1/thrums/999", headers=KAMAJI_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_thrum_with_linked_tasks(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Workflow"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Do stuff",
                "subject": "Step 1",
                "thrum_id": thrum_id,
            },
            headers=KAMAJI_HEADERS,
        )

        resp = await client.get(f"/api/v1/thrums/{thrum_id}", headers=KAMAJI_HEADERS)
        data = resp.json()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["subject"] == "Step 1"

    @pytest.mark.asyncio
    async def test_update_thrum(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/thrums/{thrum_id}",
            json={"status": "active", "plan": "Updated plan"},
            headers=KAMAJI_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["plan"] == "Updated plan"
        assert data["started_at"] is not None

    @pytest.mark.asyncio
    async def test_update_thrum_completed_sets_timestamp(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/thrums/{thrum_id}",
            json={"status": "completed", "output": "All done"},
            headers=KAMAJI_HEADERS,
        )
        data = resp.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        assert data["output"] == "All done"

    @pytest.mark.asyncio
    async def test_update_thrum_forbidden(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/thrums/{thrum_id}",
            json={"status": "active"},
            headers=JERRY_HEADERS,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_thrum_admin_can_update(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        # Ian (admin) can update anyone's thrum
        resp = await client.patch(
            f"/api/v1/thrums/{thrum_id}",
            json={"status": "paused"},
            headers=IAN_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    @pytest.mark.asyncio
    async def test_delete_thrum_admin(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/thrums/{thrum_id}",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_thrum_non_admin_forbidden(self, client):
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/thrums/{thrum_id}",
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_thrum_not_found(self, client):
        resp = await client.delete("/api/v1/thrums/999", headers=DOOT_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_kamaji_admin_can_update_tasks(self, client):
        """Verify kamaji has admin authority on tasks."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=KAMAJI_HEADERS,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_kamaji_admin_can_edit_messages(self, client):
        """Verify kamaji has admin authority on messages."""
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Hello", "subject": "Test"},
            headers=OPPY_HEADERS,
        )
        msg_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/messages/{msg_id}",
            json={"body": "Updated by kamaji"},
            headers=KAMAJI_HEADERS,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_task_with_thrum_id_via_api(self, client):
        """Creating a task with thrum_id via API includes it in response."""
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Workflow"},
            headers=KAMAJI_HEADERS,
        )
        thrum_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Do stuff",
                "thrum_id": thrum_id,
            },
            headers=KAMAJI_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=KAMAJI_HEADERS)
        assert resp.json()["thrum_id"] == thrum_id
