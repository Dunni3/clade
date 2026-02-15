"""Unit tests for conductor MCP tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from clade.mcp.tools.conductor_tools import create_conductor_tools


WORKER_REGISTRY = {
    "oppy": {
        "ember_url": "http://100.71.57.52:8100",
        "ember_api_key": "oppy-key",
        "hearth_api_key": "oppy-hearth-key",
        "working_dir": "~/projects/test",
    },
}


def _make_conductor_tools(mailbox=None, registry=None, **kwargs):
    mcp = FastMCP("test")
    return create_conductor_tools(
        mcp,
        mailbox,
        WORKER_REGISTRY if registry is None else registry,
        hearth_url="https://test.example.com",
        hearth_api_key="test-key",
        **kwargs,
    )


class TestDelegateTask:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_conductor_tools(None)
        result = await tools["delegate_task"]("oppy", "Do stuff")
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_worker(self):
        mock_client = AsyncMock()
        tools = _make_conductor_tools(mock_client)
        result = await tools["delegate_task"]("unknown", "Do stuff")
        assert "Unknown worker" in result

    @pytest.mark.asyncio
    async def test_success(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 7}
        mock_mailbox.update_task.return_value = {"id": 7, "status": "launched"}

        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            original_ember_init = conductor_tools.EmberClient.__init__
            mock_execute = AsyncMock(
                return_value={"session_name": "task-oppy-test-123", "message": "ok"}
            )

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    self.base_url = url
                    self.api_key = key
                    self.verify_ssl = verify_ssl

                async def execute_task(self, **kwargs):
                    return await mock_execute(**kwargs)

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_task"](
                "oppy", "Review the code", subject="Code review"
            )

        assert "Task #7" in result
        assert "delegated to oppy" in result
        assert "launched" in result
        mock_mailbox.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_ember_error_marks_task_failed(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 8}
        mock_mailbox.update_task.return_value = {"id": 8, "status": "failed"}

        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    self.base_url = url

                async def execute_task(self, **kwargs):
                    raise Exception("Connection refused")

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_task"]("oppy", "Do stuff")

        assert "Task #8" in result
        assert "failed" in result.lower()
        mock_mailbox.update_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_creation_error(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.side_effect = Exception("API unreachable")
        tools = _make_conductor_tools(mock_mailbox)
        result = await tools["delegate_task"]("oppy", "Do stuff")
        assert "Error creating task" in result

    @pytest.mark.asyncio
    async def test_no_ember_configured(self):
        mock_mailbox = AsyncMock()
        registry = {"oppy": {"working_dir": "~/test"}}
        tools = _make_conductor_tools(mock_mailbox, registry=registry)
        result = await tools["delegate_task"]("oppy", "Do stuff")
        assert "no Ember configured" in result


class TestCheckWorkerHealth:
    @pytest.mark.asyncio
    async def test_all_workers(self):
        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass

                async def health(self):
                    return {"active_tasks": 0, "uptime_seconds": 3600}

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mock_mailbox = AsyncMock()
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["check_worker_health"]()

        assert "oppy" in result
        assert "Healthy" in result

    @pytest.mark.asyncio
    async def test_single_worker(self):
        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass

                async def health(self):
                    return {"active_tasks": 1, "uptime_seconds": 100}

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mock_mailbox = AsyncMock()
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["check_worker_health"](brother="oppy")

        assert "oppy" in result
        assert "Healthy" in result

    @pytest.mark.asyncio
    async def test_unknown_worker(self):
        mock_mailbox = AsyncMock()
        tools = _make_conductor_tools(mock_mailbox)
        result = await tools["check_worker_health"](brother="unknown")
        assert "Unknown worker" in result

    @pytest.mark.asyncio
    async def test_unreachable(self):
        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass

                async def health(self):
                    raise Exception("Connection refused")

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mock_mailbox = AsyncMock()
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["check_worker_health"]()

        assert "Unreachable" in result

    @pytest.mark.asyncio
    async def test_no_workers(self):
        mock_mailbox = AsyncMock()
        tools = _make_conductor_tools(mock_mailbox, registry={})
        result = await tools["check_worker_health"]()
        assert "No workers configured" in result


class TestListWorkerTasks:
    @pytest.mark.asyncio
    async def test_idle(self):
        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass

                async def active_tasks(self):
                    return {"active_task": None, "orphaned_sessions": []}

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mock_mailbox = AsyncMock()
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["list_worker_tasks"]()

        assert "Idle" in result

    @pytest.mark.asyncio
    async def test_active(self):
        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass

                async def active_tasks(self):
                    return {
                        "active_task": {
                            "task_id": 5,
                            "subject": "Training run",
                            "session_name": "task-oppy-train-123",
                        },
                        "orphaned_sessions": [],
                    }

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mock_mailbox = AsyncMock()
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["list_worker_tasks"]()

        assert "Active" in result
        assert "Training run" in result

    @pytest.mark.asyncio
    async def test_error(self):
        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass

                async def active_tasks(self):
                    raise Exception("Timeout")

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mock_mailbox = AsyncMock()
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["list_worker_tasks"]()

        assert "Unreachable" in result
