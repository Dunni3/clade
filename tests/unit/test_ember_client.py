"""Tests for the EmberClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clade.worker.client import EmberClient


@pytest.fixture
def client():
    return EmberClient("http://localhost:8100", "test-key", verify_ssl=False)


class TestEmberClientInit:
    def test_strips_trailing_slash(self):
        c = EmberClient("http://localhost:8100/", "key")
        assert c.base_url == "http://localhost:8100"

    def test_auth_header(self):
        c = EmberClient("http://localhost:8100", "my-key")
        assert c.headers["Authorization"] == "Bearer my-key"


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_success(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": "ok",
            "brother": "oppy",
            "active_tasks": 0,
            "uptime_seconds": 42.0,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("clade.worker.client.httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.health()
            assert result["status"] == "ok"
            assert result["brother"] == "oppy"
            # No auth header for health
            mock_ctx.get.assert_called_once()
            call_kwargs = mock_ctx.get.call_args
            assert "headers" not in call_kwargs.kwargs or call_kwargs.kwargs.get("headers") is None


class TestExecuteTask:
    @pytest.mark.asyncio
    async def test_execute_task(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "launched",
            "session_name": "task-oppy-test-123",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("clade.worker.client.httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.execute_task(
                prompt="do stuff",
                subject="Test task",
                task_id=42,
            )
            assert result["status"] == "launched"
            # Check auth header was sent
            call_kwargs = mock_ctx.post.call_args
            assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_execute_task_minimal(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "launched"}
        mock_resp.raise_for_status = MagicMock()

        with patch("clade.worker.client.httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.execute_task(prompt="do stuff")
            payload = mock_ctx.post.call_args.kwargs["json"]
            assert payload["prompt"] == "do stuff"
            assert "task_id" not in payload
            assert "working_dir" not in payload
            assert "target_branch" not in payload

    @pytest.mark.asyncio
    async def test_execute_task_with_target_branch(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "launched"}
        mock_resp.raise_for_status = MagicMock()

        with patch("clade.worker.client.httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.execute_task(
                prompt="do stuff",
                target_branch="card-5-sudoers",
            )
            payload = mock_ctx.post.call_args.kwargs["json"]
            assert payload["target_branch"] == "card-5-sudoers"


class TestActiveTasks:
    @pytest.mark.asyncio
    async def test_active_tasks(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "active_task": None,
            "orphaned_sessions": ["task-oppy-old-123"],
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("clade.worker.client.httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.active_tasks()
            assert result["active_task"] is None
            assert len(result["orphaned_sessions"]) == 1
