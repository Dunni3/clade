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


def _mock_ember_client_patcher(mp, mock_execute=None):
    """Patch EmberClient with a mock that delegates to mock_execute."""
    from clade.mcp.tools import conductor_tools

    if mock_execute is None:
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
    return mock_execute


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
            _mock_ember_client_patcher(mp)
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
    async def test_trigger_env_ignored_by_delegate_task(self):
        """delegate_task no longer reads TRIGGER_TASK_ID — that's delegate_child_task's job."""
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 20}
        mock_mailbox.update_task.return_value = {"id": 20, "status": "launched"}

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRIGGER_TASK_ID", "42")
            _mock_ember_client_patcher(mp)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_task"]("oppy", "Do stuff")

        assert "Task #20" in result
        call_kwargs = mock_mailbox.create_task.call_args
        # delegate_task should NOT auto-link from TRIGGER_TASK_ID
        assert call_kwargs.kwargs["parent_task_id"] is None

    @pytest.mark.asyncio
    async def test_explicit_parent(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 21}
        mock_mailbox.update_task.return_value = {"id": 21, "status": "launched"}

        with pytest.MonkeyPatch.context() as mp:
            _mock_ember_client_patcher(mp)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_task"](
                "oppy", "Do stuff", parent_task_id=99
            )

        assert "Task #21" in result
        call_kwargs = mock_mailbox.create_task.call_args
        assert call_kwargs.kwargs["parent_task_id"] == 99


class TestDelegateChildTask:
    """Tests for the new delegate_child_task tool."""

    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_conductor_tools(None)
        result = await tools["delegate_child_task"]("oppy", "Do stuff")
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_worker(self):
        mock_client = AsyncMock()
        tools = _make_conductor_tools(mock_client)
        result = await tools["delegate_child_task"]("unknown", "Do stuff")
        assert "Unknown worker" in result

    @pytest.mark.asyncio
    async def test_requires_parent_error(self):
        """Should error if no parent_task_ids and no TRIGGER_TASK_ID."""
        mock_mailbox = AsyncMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("TRIGGER_TASK_ID", raising=False)
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"]("oppy", "Do stuff")
        assert "requires a parent" in result.lower()

    @pytest.mark.asyncio
    async def test_auto_parent_from_trigger_env(self):
        """Should auto-link parent from TRIGGER_TASK_ID when no explicit parents."""
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 30}
        mock_mailbox.update_task.return_value = {"id": 30, "status": "launched"}
        mock_mailbox.get_task.return_value = {
            "id": 42,
            "subject": "Parent task",
            "status": "completed",
            "output": "All done",
            "depth": 0,
            "root_task_id": 42,
            "project": "clade",
            "linked_cards": [{"id": 60, "title": "Test card"}],
            "metadata": None,
        }

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRIGGER_TASK_ID", "42")
            _mock_ember_client_patcher(mp)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"]("oppy", "Follow up")

        assert "Task #30" in result
        call_kwargs = mock_mailbox.create_task.call_args
        assert call_kwargs.kwargs["parent_task_ids"] == [42]

    @pytest.mark.asyncio
    async def test_explicit_parents(self):
        """Should use explicitly provided parent_task_ids."""
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 31}
        mock_mailbox.update_task.return_value = {"id": 31, "status": "launched"}
        mock_mailbox.get_task.return_value = {
            "id": 10,
            "subject": "Parent",
            "status": "completed",
            "output": "Done",
            "depth": 1,
            "root_task_id": 5,
            "project": "clade",
            "linked_cards": [],
            "metadata": None,
        }

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRIGGER_TASK_ID", "99")  # Should be ignored
            _mock_ember_client_patcher(mp)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"](
                "oppy", "Follow up", parent_task_ids=[10]
            )

        assert "Task #31" in result
        call_kwargs = mock_mailbox.create_task.call_args
        assert call_kwargs.kwargs["parent_task_ids"] == [10]

    @pytest.mark.asyncio
    async def test_depth_guard(self):
        """Should block tasks that exceed max_depth."""
        mock_mailbox = AsyncMock()
        # Parent at depth 2, root has max_depth=2
        mock_mailbox.get_task.side_effect = [
            # First call: parent task
            {
                "id": 50,
                "subject": "Deep task",
                "status": "completed",
                "output": "Done",
                "depth": 2,
                "root_task_id": 40,
                "project": "clade",
                "linked_cards": [],
                "metadata": None,
            },
            # Second call: root task
            {
                "id": 40,
                "subject": "Root",
                "status": "completed",
                "output": "",
                "depth": 0,
                "root_task_id": 40,
                "project": "clade",
                "linked_cards": [],
                "metadata": {"max_depth": 2},
            },
        ]

        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("TRIGGER_TASK_ID", raising=False)
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"](
                "oppy", "Too deep", parent_task_ids=[50]
            )

        assert "Depth guard" in result
        assert "max_depth=2" in result

    @pytest.mark.asyncio
    async def test_auto_inherit_card_id(self):
        """Should inherit card_id from primary parent's linked cards."""
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 32}
        mock_mailbox.update_task.return_value = {"id": 32, "status": "launched"}
        mock_mailbox.get_task.return_value = {
            "id": 10,
            "subject": "Parent",
            "status": "completed",
            "output": "Done",
            "depth": 0,
            "root_task_id": 10,
            "project": "clade",
            "linked_cards": [{"id": 60, "title": "Test card"}],
            "metadata": None,
        }
        mock_mailbox.add_card_link.return_value = {}

        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("TRIGGER_TASK_ID", raising=False)
            _mock_ember_client_patcher(mp)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"](
                "oppy", "Follow up", parent_task_ids=[10]
            )

        assert "Task #32" in result
        # Should have linked to inherited card
        mock_mailbox.add_card_link.assert_called_once_with(60, "task", "32")

    @pytest.mark.asyncio
    async def test_auto_inherit_project(self):
        """Should inherit project from primary parent."""
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 33}
        mock_mailbox.update_task.return_value = {"id": 33, "status": "launched"}
        mock_mailbox.get_task.return_value = {
            "id": 10,
            "subject": "Parent",
            "status": "completed",
            "output": "Done",
            "depth": 0,
            "root_task_id": 10,
            "project": "omtra",
            "linked_cards": [],
            "metadata": None,
        }

        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("TRIGGER_TASK_ID", raising=False)
            _mock_ember_client_patcher(mp)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"](
                "oppy", "Follow up", parent_task_ids=[10]
            )

        assert "Task #33" in result
        call_kwargs = mock_mailbox.create_task.call_args
        assert call_kwargs.kwargs["project"] == "omtra"

    @pytest.mark.asyncio
    async def test_multi_parent_context_injection(self):
        """Should prepend parent summaries into prompt for multi-parent joins."""
        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 34}
        mock_mailbox.update_task.return_value = {"id": 34, "status": "launched"}
        mock_mailbox.get_task.side_effect = [
            # Parent 1
            {
                "id": 10,
                "subject": "Research A",
                "status": "completed",
                "output": "Found approach A",
                "depth": 1,
                "root_task_id": 5,
                "project": "clade",
                "linked_cards": [],
                "metadata": None,
            },
            # Parent 2
            {
                "id": 11,
                "subject": "Research B",
                "status": "completed",
                "output": "Found approach B",
                "depth": 1,
                "root_task_id": 5,
                "project": "clade",
                "linked_cards": [],
                "metadata": None,
            },
            # Root task (for depth guard)
            {
                "id": 5,
                "subject": "Root",
                "status": "completed",
                "output": "",
                "depth": 0,
                "root_task_id": 5,
                "metadata": None,
            },
        ]

        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("TRIGGER_TASK_ID", raising=False)
            _mock_ember_client_patcher(mp)

            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"](
                "oppy", "Synthesize findings",
                parent_task_ids=[10, 11],
            )

        assert "Task #34" in result
        # The prompt should include parent context
        call_kwargs = mock_mailbox.create_task.call_args
        augmented_prompt = call_kwargs.kwargs["prompt"]
        assert "Parent #10" in augmented_prompt
        assert "Research A" in augmented_prompt
        assert "Parent #11" in augmented_prompt
        assert "Research B" in augmented_prompt
        assert "Synthesize findings" in augmented_prompt

    @pytest.mark.asyncio
    async def test_invalid_trigger_env(self):
        """Invalid TRIGGER_TASK_ID should result in 'requires parent' error."""
        mock_mailbox = AsyncMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRIGGER_TASK_ID", "abc")
            tools = _make_conductor_tools(mock_mailbox)
            result = await tools["delegate_child_task"]("oppy", "Do stuff")
        assert "requires a parent" in result.lower()

    @pytest.mark.asyncio
    async def test_no_ember_configured(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_task.return_value = {
            "id": 10,
            "subject": "Parent",
            "status": "completed",
            "output": "",
            "depth": 0,
            "root_task_id": 10,
            "project": None,
            "linked_cards": [],
            "metadata": None,
        }
        registry = {"oppy": {"working_dir": "~/test"}}
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("TRIGGER_TASK_ID", raising=False)
            tools = _make_conductor_tools(mock_mailbox, registry=registry)
            result = await tools["delegate_child_task"](
                "oppy", "Do stuff", parent_task_ids=[10]
            )
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
