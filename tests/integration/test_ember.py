"""Integration tests for the Ember server endpoints."""

from unittest.mock import patch, MagicMock

import pytest
import httpx

from clade.worker.ember import app, _state, ActiveTask
from clade.worker.runner import LocalTaskResult


@pytest.fixture(autouse=True)
def reset_state():
    """Reset in-memory state between tests."""
    _state.active = None
    _state._history = []
    yield
    _state.active = None
    _state._history = []


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-hearth-key"}


@pytest.fixture
def env_vars():
    return {
        "HEARTH_API_KEY": "test-hearth-key",
        "EMBER_BROTHER_NAME": "oppy",
    }


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_no_auth(self):
        """Health endpoint should work without authentication."""
        with patch.dict("os.environ", {"HEARTH_API_KEY": "key"}):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/health")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ok"
                assert "brother" in data
                assert "uptime_seconds" in data

    @pytest.mark.asyncio
    @patch("clade.worker.ember._state")
    async def test_health_shows_active_count(self, mock_state):
        mock_state.is_busy.return_value = True
        with patch.dict("os.environ", {"HEARTH_API_KEY": "key"}):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/health")
                data = resp.json()
                assert data["active_tasks"] == 1


class TestExecuteEndpoint:
    @pytest.mark.asyncio
    async def test_execute_success(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.launch_local_task") as mock_launch:
                mock_launch.return_value = LocalTaskResult(
                    success=True,
                    session_name="task-oppy-test-123",
                    message="Task launched",
                )
                with patch("clade.worker.ember.check_tmux_session", return_value=False):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://test",
                    ) as client:
                        resp = await client.post(
                            "/tasks/execute",
                            json={"prompt": "do stuff", "subject": "Test"},
                            headers=auth_headers,
                        )
                        assert resp.status_code == 202
                        data = resp.json()
                        assert data["status"] == "launched"

    @pytest.mark.asyncio
    async def test_execute_busy_409(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.check_tmux_session", return_value=True):
                # Set up an active task
                _state.set_active(ActiveTask(
                    task_id=1,
                    session_name="task-oppy-existing-123",
                    subject="Existing task",
                    started_at=1000000,
                ))
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.post(
                        "/tasks/execute",
                        json={"prompt": "do more stuff"},
                        headers=auth_headers,
                    )
                    # The endpoint returns 202 with error payload (not a 409 HTTP status)
                    assert resp.status_code == 202
                    data = resp.json()
                    assert data["error"] == "busy"

    @pytest.mark.asyncio
    async def test_execute_launch_failure(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.launch_local_task") as mock_launch:
                mock_launch.return_value = LocalTaskResult(
                    success=False,
                    session_name="task-oppy-fail-123",
                    message="tmux not found",
                    stderr="command not found: tmux",
                )
                with patch("clade.worker.ember.check_tmux_session", return_value=False):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://test",
                    ) as client:
                        resp = await client.post(
                            "/tasks/execute",
                            json={"prompt": "do stuff"},
                            headers=auth_headers,
                        )
                        assert resp.status_code == 202
                        data = resp.json()
                        assert data["error"] == "launch_failed"

    @pytest.mark.asyncio
    async def test_execute_no_auth(self, env_vars):
        with patch.dict("os.environ", env_vars):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/tasks/execute",
                    json={"prompt": "do stuff"},
                )
                assert resp.status_code == 422  # Missing header

    @pytest.mark.asyncio
    async def test_execute_bad_auth(self, env_vars):
        with patch.dict("os.environ", env_vars):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/tasks/execute",
                    json={"prompt": "do stuff"},
                    headers={"Authorization": "Bearer wrong-key"},
                )
                assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_execute_wraps_prompt_with_task_id(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.launch_local_task") as mock_launch:
                mock_launch.return_value = LocalTaskResult(
                    success=True,
                    session_name="task-oppy-test-123",
                    message="Task launched",
                )
                with patch("clade.worker.ember.check_tmux_session", return_value=False):
                    with patch("clade.worker.ember.wrap_prompt") as mock_wrap:
                        mock_wrap.return_value = "wrapped prompt"
                        async with httpx.AsyncClient(
                            transport=httpx.ASGITransport(app=app),
                            base_url="http://test",
                        ) as client:
                            await client.post(
                                "/tasks/execute",
                                json={
                                    "prompt": "original",
                                    "subject": "Test",
                                    "task_id": 42,
                                },
                                headers=auth_headers,
                            )
                        mock_wrap.assert_called_once()
                        # sender_name should default to "unknown" when not provided
                        call_kwargs = mock_wrap.call_args
                        assert call_kwargs.kwargs.get("sender_name") == "unknown" or \
                            call_kwargs[1].get("sender_name") == "unknown"
                        # The wrapped prompt should be passed to launch
                        launch_kwargs = mock_launch.call_args
                        assert launch_kwargs.kwargs["prompt"] == "wrapped prompt" or \
                            launch_kwargs[1].get("prompt") == "wrapped prompt" or \
                            (len(launch_kwargs[0]) > 2 and launch_kwargs[0][2] == "wrapped prompt")

    @pytest.mark.asyncio
    async def test_execute_passes_sender_name(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.launch_local_task") as mock_launch:
                mock_launch.return_value = LocalTaskResult(
                    success=True,
                    session_name="task-oppy-test-123",
                    message="Task launched",
                )
                with patch("clade.worker.ember.check_tmux_session", return_value=False):
                    with patch("clade.worker.ember.wrap_prompt") as mock_wrap:
                        mock_wrap.return_value = "wrapped prompt"
                        async with httpx.AsyncClient(
                            transport=httpx.ASGITransport(app=app),
                            base_url="http://test",
                        ) as client:
                            await client.post(
                                "/tasks/execute",
                                json={
                                    "prompt": "original",
                                    "subject": "Test",
                                    "task_id": 42,
                                    "sender_name": "kamaji",
                                },
                                headers=auth_headers,
                            )
                        # sender_name should be passed through from request
                        call_kwargs = mock_wrap.call_args
                        assert call_kwargs.kwargs.get("sender_name") == "kamaji" or \
                            call_kwargs[1].get("sender_name") == "kamaji"


class TestActiveTasksEndpoint:
    @pytest.mark.asyncio
    async def test_no_active_tasks(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.list_tmux_sessions", return_value=[]):
                with patch("clade.worker.ember.check_tmux_session", return_value=False):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://test",
                    ) as client:
                        resp = await client.get(
                            "/tasks/active",
                            headers=auth_headers,
                        )
                        assert resp.status_code == 200
                        data = resp.json()
                        assert data["active_task"] is None

    @pytest.mark.asyncio
    async def test_with_active_task(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.check_tmux_session", return_value=True):
                _state.set_active(ActiveTask(
                    task_id=42,
                    session_name="task-oppy-review-123",
                    subject="Review code",
                    started_at=1000000,
                ))
                with patch("clade.worker.ember.list_tmux_sessions", return_value=["task-oppy-review-123"]):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://test",
                    ) as client:
                        resp = await client.get(
                            "/tasks/active",
                            headers=auth_headers,
                        )
                        data = resp.json()
                        assert data["active_task"]["task_id"] == 42
                        # Active session should be filtered from orphaned list
                        assert "task-oppy-review-123" not in data["orphaned_sessions"]

    @pytest.mark.asyncio
    async def test_orphaned_sessions(self, auth_headers, env_vars):
        with patch.dict("os.environ", env_vars):
            with patch("clade.worker.ember.check_tmux_session", return_value=False):
                with patch(
                    "clade.worker.ember.list_tmux_sessions",
                    return_value=["task-oppy-old-1", "task-oppy-old-2"],
                ):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://test",
                    ) as client:
                        resp = await client.get(
                            "/tasks/active",
                            headers=auth_headers,
                        )
                        data = resp.json()
                        assert data["active_task"] is None
                        assert len(data["orphaned_sessions"]) == 2

    @pytest.mark.asyncio
    async def test_active_tasks_no_auth(self, env_vars):
        with patch.dict("os.environ", env_vars):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/tasks/active")
                assert resp.status_code == 422  # Missing header
