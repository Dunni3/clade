"""Tests for event-driven conductor tick triggering from the Hearth."""

import os
from unittest.mock import MagicMock, patch

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
KAMAJI_HEADERS = {"Authorization": "Bearer test-key-kamaji"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}


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
# Helpers
# ---------------------------------------------------------------------------


async def _create_thrum_and_task(client, thrum_id=None):
    """Create a thrum with a linked task, return (thrum_id, task_id)."""
    if thrum_id is None:
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test workflow"},
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
    return thrum_id, task_id


# ---------------------------------------------------------------------------
# Tests — task completion triggers
# ---------------------------------------------------------------------------


class TestConductorTriggerOnTaskUpdate:
    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen")
    async def test_thrum_linked_task_completed_triggers(self, mock_popen, client):
        """Completing a thrum-linked task should fire the conductor tick."""
        _, task_id = await _create_thrum_and_task(client)
        mock_popen.reset_mock()  # clear call from thrum creation

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "Done"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        mock_popen.assert_called_once_with(
            "echo tick",
            shell=True,
            stdout=-3,  # subprocess.DEVNULL
            stderr=-3,
            start_new_session=True,
        )

    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen")
    async def test_thrum_linked_task_failed_triggers(self, mock_popen, client):
        """Failing a thrum-linked task should fire the conductor tick."""
        _, task_id = await _create_thrum_and_task(client)
        mock_popen.reset_mock()  # clear call from thrum creation

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "failed", "output": "Error"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        mock_popen.assert_called_once()

    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen")
    async def test_standalone_task_completed_no_trigger(self, mock_popen, client):
        """Completing a task without thrum_id should NOT trigger."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Standalone task"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "Done"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        mock_popen.assert_not_called()

    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen")
    async def test_task_in_progress_no_trigger(self, mock_popen, client):
        """Setting a thrum-linked task to in_progress should NOT trigger."""
        _, task_id = await _create_thrum_and_task(client)
        mock_popen.reset_mock()  # clear call from thrum creation

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        mock_popen.assert_not_called()

    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen")
    async def test_task_launched_no_trigger(self, mock_popen, client):
        """Setting a thrum-linked task to launched should NOT trigger."""
        _, task_id = await _create_thrum_and_task(client)
        mock_popen.reset_mock()  # clear call from thrum creation

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "launched"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — thrum creation triggers
# ---------------------------------------------------------------------------


class TestConductorTriggerOnThrumCreate:
    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen")
    async def test_new_thrum_triggers(self, mock_popen, client):
        """Creating a new thrum should fire the conductor tick."""
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "New workflow", "goal": "Test trigger"},
            headers=KAMAJI_HEADERS,
        )
        assert resp.status_code == 200
        mock_popen.assert_called_once()


# ---------------------------------------------------------------------------
# Tests — no-op when unconfigured
# ---------------------------------------------------------------------------


class TestConductorTriggerDisabled:
    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", None)
    @patch("hearth.app.subprocess.Popen")
    async def test_no_cmd_no_subprocess_on_task(self, mock_popen, client):
        """Without CONDUCTOR_TICK_CMD, no subprocess is spawned on task completion."""
        _, task_id = await _create_thrum_and_task(client)
        mock_popen.reset_mock()  # clear any calls from setup

        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "Done"},
            headers=OPPY_HEADERS,
        )
        mock_popen.assert_not_called()

    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", None)
    @patch("hearth.app.subprocess.Popen")
    async def test_no_cmd_no_subprocess_on_thrum(self, mock_popen, client):
        """Without CONDUCTOR_TICK_CMD, no subprocess is spawned on thrum creation."""
        await client.post(
            "/api/v1/thrums",
            json={"title": "Test"},
            headers=KAMAJI_HEADERS,
        )
        mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — error resilience
# ---------------------------------------------------------------------------


class TestConductorTriggerErrorResilience:
    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen", side_effect=OSError("spawn failed"))
    async def test_popen_exception_does_not_crash_api(self, mock_popen, client):
        """If Popen raises, the API response still succeeds."""
        _, task_id = await _create_thrum_and_task(client)
        mock_popen.reset_mock()  # clear call from thrum creation

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "Done"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    @patch("hearth.app.CONDUCTOR_TICK_CMD", "echo tick")
    @patch("hearth.app.subprocess.Popen", side_effect=OSError("spawn failed"))
    async def test_popen_exception_on_thrum_create_does_not_crash(self, mock_popen, client):
        """If Popen raises during thrum creation, the API still succeeds."""
        resp = await client.post(
            "/api/v1/thrums",
            json={"title": "Test", "goal": "Resilience test"},
            headers=KAMAJI_HEADERS,
        )
        assert resp.status_code == 200
        assert "id" in resp.json()
