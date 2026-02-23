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
    async def test_ember_error_and_status_update_fails_warns_orphaned(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 9}

        async def update_task_raises(*args, **kwargs):
            raise Exception("Hearth unreachable")

        mock_mailbox.update_task = update_task_raises

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

        assert "Task #9" in result
        assert "orphaned" in result.lower()
        assert "WARNING" in result

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

    @pytest.mark.asyncio
    async def test_auto_parent_from_env(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 20}
        mock_mailbox.update_task.return_value = {"id": 20, "status": "launched"}

        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            mp.setenv("TRIGGER_TASK_ID", "42")

            mock_execute = AsyncMock(
                return_value={"session_name": "task-oppy-test-abc", "message": "ok"}
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
            result = await tools["delegate_task"]("oppy", "Do stuff")

        assert "Task #20" in result
        # Verify parent_task_id was passed through to create_task
        call_kwargs = mock_mailbox.create_task.call_args
        assert call_kwargs.kwargs["parent_task_id"] == 42

    @pytest.mark.asyncio
    async def test_explicit_parent_overrides_env(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 21}
        mock_mailbox.update_task.return_value = {"id": 21, "status": "launched"}

        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            mp.setenv("TRIGGER_TASK_ID", "42")

            mock_execute = AsyncMock(
                return_value={"session_name": "task-oppy-test-def", "message": "ok"}
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
                "oppy", "Do stuff", parent_task_id=99
            )

        assert "Task #21" in result
        call_kwargs = mock_mailbox.create_task.call_args
        # Explicit parent_task_id=99 should win over env TRIGGER_TASK_ID=42
        assert call_kwargs.kwargs["parent_task_id"] == 99

    @pytest.mark.asyncio
    async def test_invalid_trigger_id_ignored(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 22}
        mock_mailbox.update_task.return_value = {"id": 22, "status": "launched"}

        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            mp.setenv("TRIGGER_TASK_ID", "abc")

            mock_execute = AsyncMock(
                return_value={"session_name": "task-oppy-test-ghi", "message": "ok"}
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
            result = await tools["delegate_task"]("oppy", "Do stuff")

        assert "Task #22" in result
        call_kwargs = mock_mailbox.create_task.call_args
        # Invalid env value should result in parent_task_id=None
        assert call_kwargs.kwargs["parent_task_id"] is None

    @pytest.mark.asyncio
    async def test_no_trigger_env(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 23}
        mock_mailbox.update_task.return_value = {"id": 23, "status": "launched"}

        with pytest.MonkeyPatch.context() as mp:
            from clade.mcp.tools import conductor_tools

            mp.delenv("TRIGGER_TASK_ID", raising=False)

            mock_execute = AsyncMock(
                return_value={"session_name": "task-oppy-test-jkl", "message": "ok"}
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
            result = await tools["delegate_task"]("oppy", "Do stuff")

        assert "Task #23" in result
        call_kwargs = mock_mailbox.create_task.call_args
        assert call_kwargs.kwargs["parent_task_id"] is None


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
                    return {"aspens": [], "orphaned_sessions": []}

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
                        "aspens": [
                            {
                                "task_id": 5,
                                "subject": "Training run",
                                "session_name": "task-oppy-train-123",
                            },
                        ],
                        "orphaned_sessions": [],
                    }

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mock_mailbox = AsyncMock()
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["list_worker_tasks"]()

        assert "1 active aspen" in result
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
