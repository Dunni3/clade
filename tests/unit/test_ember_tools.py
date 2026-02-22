"""Tests for Ember MCP tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.server.fastmcp import FastMCP

from clade.mcp.tools.ember_tools import create_ember_tools
from clade.worker.client import EmberClient


@pytest.fixture
def mcp():
    return FastMCP("test")


class TestCheckEmberHealth:
    @pytest.mark.asyncio
    async def test_configured_healthy(self, mcp):
        mock_ember = AsyncMock(spec=EmberClient)
        mock_ember.health.return_value = {
            "status": "ok",
            "brother": "oppy",
            "active_tasks": 0,
            "uptime_seconds": 100.0,
        }
        tools = create_ember_tools(mcp, mock_ember)
        result = await tools["check_ember_health"](url=None)
        assert "healthy" in result
        assert "oppy" in result

    @pytest.mark.asyncio
    async def test_configured_error(self, mcp):
        mock_ember = AsyncMock(spec=EmberClient)
        mock_ember.health.side_effect = Exception("connection refused")
        tools = create_ember_tools(mcp, mock_ember)
        result = await tools["check_ember_health"](url=None)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_not_configured(self, mcp):
        tools = create_ember_tools(mcp, None)
        result = await tools["check_ember_health"](url=None)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_url_override(self, mcp):
        tools = create_ember_tools(mcp, None)
        # Even with no configured ember, ad-hoc URL should be tried
        with patch("clade.mcp.tools.ember_tools.EmberClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.health.return_value = {
                "status": "ok",
                "brother": "jerry",
                "active_tasks": 1,
                "uptime_seconds": 50.0,
            }
            mock_cls.return_value = mock_instance
            result = await tools["check_ember_health"](url="http://10.0.0.5:8100")
            assert "healthy" in result
            assert "jerry" in result

    @pytest.mark.asyncio
    async def test_url_override_unreachable(self, mcp):
        tools = create_ember_tools(mcp, None)
        with patch("clade.mcp.tools.ember_tools.EmberClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.health.side_effect = Exception("connection refused")
            mock_cls.return_value = mock_instance
            result = await tools["check_ember_health"](url="http://10.0.0.5:8100")
            assert "unreachable" in result


class TestListEmberTasks:
    @pytest.mark.asyncio
    async def test_with_active_task(self, mcp):
        mock_ember = AsyncMock(spec=EmberClient)
        mock_ember.active_tasks.return_value = {
            "aspens": [
                {
                    "task_id": 42,
                    "session_name": "task-oppy-review-123",
                    "subject": "Review code",
                    "working_dir": "~/projects/test",
                    "alive": True,
                },
            ],
            "orphaned_sessions": [],
        }
        tools = create_ember_tools(mcp, mock_ember)
        result = await tools["list_ember_tasks"]()
        assert "active aspen" in result
        assert "42" in result
        assert "Review code" in result

    @pytest.mark.asyncio
    async def test_no_active_task(self, mcp):
        mock_ember = AsyncMock(spec=EmberClient)
        mock_ember.active_tasks.return_value = {
            "aspens": [],
            "orphaned_sessions": [],
        }
        tools = create_ember_tools(mcp, mock_ember)
        result = await tools["list_ember_tasks"]()
        assert "No active aspens" in result

    @pytest.mark.asyncio
    async def test_orphaned_sessions(self, mcp):
        mock_ember = AsyncMock(spec=EmberClient)
        mock_ember.active_tasks.return_value = {
            "aspens": [],
            "orphaned_sessions": ["task-oppy-old-1", "task-oppy-old-2"],
        }
        tools = create_ember_tools(mcp, mock_ember)
        result = await tools["list_ember_tasks"]()
        assert "Orphaned" in result
        assert "task-oppy-old-1" in result
        assert "task-oppy-old-2" in result

    @pytest.mark.asyncio
    async def test_not_configured(self, mcp):
        tools = create_ember_tools(mcp, None)
        result = await tools["list_ember_tasks"]()
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_error(self, mcp):
        mock_ember = AsyncMock(spec=EmberClient)
        mock_ember.active_tasks.side_effect = Exception("timeout")
        tools = create_ember_tools(mcp, mock_ember)
        result = await tools["list_ember_tasks"]()
        assert "Error" in result
