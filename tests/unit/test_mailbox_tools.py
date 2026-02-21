"""Unit tests for mailbox MCP tools."""

from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from clade.mcp.tools.mailbox_tools import create_mailbox_tools


def _make_tools(mailbox=None):
    mcp = FastMCP("test")
    return create_mailbox_tools(mcp, mailbox)


class TestDepositMorsel:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_tools(None)
        result = await tools["deposit_morsel"]("A note")
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_basic(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_morsel.return_value = {"id": 1}
        tools = _make_tools(mock_mailbox)
        result = await tools["deposit_morsel"]("A simple note")
        assert "Morsel #1 deposited" in result
        mock_mailbox.create_morsel.assert_called_once_with(
            body="A simple note", tags=None, links=None
        )

    @pytest.mark.asyncio
    async def test_with_tags(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_morsel.return_value = {"id": 2}
        tools = _make_tools(mock_mailbox)
        result = await tools["deposit_morsel"]("Tagged note", tags=["debug", "test"])
        assert "Morsel #2 deposited" in result
        call_kwargs = mock_mailbox.create_morsel.call_args
        assert call_kwargs.kwargs["tags"] == ["debug", "test"]

    @pytest.mark.asyncio
    async def test_with_task_link(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_morsel.return_value = {"id": 3}
        tools = _make_tools(mock_mailbox)
        result = await tools["deposit_morsel"]("Linked note", task_id=42)
        assert "Morsel #3 deposited" in result
        call_kwargs = mock_mailbox.create_morsel.call_args
        links = call_kwargs.kwargs["links"]
        assert links == [{"object_type": "task", "object_id": "42"}]

    @pytest.mark.asyncio
    async def test_error_handling(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.create_morsel.side_effect = Exception("Connection refused")
        tools = _make_tools(mock_mailbox)
        result = await tools["deposit_morsel"]("A note")
        assert "Error depositing morsel" in result
        assert "Connection refused" in result


class TestListTrees:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_tools(None)
        result = await tools["list_trees"]()
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_empty(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_trees.return_value = []
        tools = _make_tools(mock_mailbox)
        result = await tools["list_trees"]()
        assert "No task trees found" in result

    @pytest.mark.asyncio
    async def test_with_trees(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_trees.return_value = [
            {
                "root": {"id": 10, "subject": "Deploy pipeline", "assignee": "kamaji"},
                "total_tasks": 4,
                "status_counts": {"completed": 3, "in_progress": 1},
            },
        ]
        tools = _make_tools(mock_mailbox)
        result = await tools["list_trees"]()
        assert "Tree #10" in result
        assert "Deploy pipeline" in result
        assert "Tasks: 4" in result
        assert "completed: 3" in result


class TestGetTree:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_tools(None)
        result = await tools["get_tree"](1)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_renders_hierarchy(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_tree.return_value = {
            "root": {
                "id": 1,
                "subject": "Root task",
                "assignee": "kamaji",
                "status": "completed",
                "children": [
                    {
                        "id": 2,
                        "subject": "Child A",
                        "assignee": "oppy",
                        "status": "completed",
                        "children": [
                            {
                                "id": 4,
                                "subject": "Grandchild",
                                "assignee": "oppy",
                                "status": "in_progress",
                                "children": [],
                            },
                        ],
                    },
                    {
                        "id": 3,
                        "subject": "Child B",
                        "assignee": "jerry",
                        "status": "completed",
                        "children": [],
                    },
                ],
            }
        }
        tools = _make_tools(mock_mailbox)
        result = await tools["get_tree"](1)
        assert "#1" in result
        assert "Root task" in result
        assert "#2" in result
        assert "Child A" in result
        assert "#3" in result
        assert "Child B" in result
        assert "#4" in result
        assert "Grandchild" in result


class TestListMorsels:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        tools = _make_tools(None)
        result = await tools["list_morsels"]()
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_empty(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_morsels.return_value = []
        tools = _make_tools(mock_mailbox)
        result = await tools["list_morsels"]()
        assert "No morsels found" in result

    @pytest.mark.asyncio
    async def test_with_morsels(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_morsels.return_value = [
            {
                "id": 1,
                "creator": "oppy",
                "body": "Observed high loss on epoch 5",
                "tags": ["training", "debug"],
                "created_at": "2026-02-20T10:00:00Z",
            },
            {
                "id": 2,
                "creator": "doot",
                "body": "Config updated for retry",
                "tags": [],
                "created_at": "2026-02-20T11:00:00Z",
            },
        ]
        tools = _make_tools(mock_mailbox)
        result = await tools["list_morsels"]()
        assert "#1 by oppy" in result
        assert "training, debug" in result
        assert "Observed high loss" in result
        assert "#2 by doot" in result
        assert "Config updated" in result

    @pytest.mark.asyncio
    async def test_filter_by_task(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_morsels.return_value = [
            {
                "id": 5,
                "creator": "oppy",
                "body": "Task-linked morsel",
                "tags": [],
                "created_at": "2026-02-20T12:00:00Z",
            },
        ]
        tools = _make_tools(mock_mailbox)
        result = await tools["list_morsels"](task_id=42)
        assert "#5 by oppy" in result
        call_kwargs = mock_mailbox.get_morsels.call_args
        assert call_kwargs.kwargs["object_type"] == "task"
        assert call_kwargs.kwargs["object_id"] == 42


class TestGetTaskEnhanced:
    @pytest.mark.asyncio
    async def test_shows_parent_and_children(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_task.return_value = {
            "id": 10,
            "status": "completed",
            "subject": "Parent task",
            "assignee": "kamaji",
            "creator": "doot",
            "created_at": "2026-02-20T10:00:00Z",
            "completed_at": "2026-02-20T11:00:00Z",
            "parent_task_id": 5,
            "root_task_id": 1,
            "thrum_id": None,
            "host": None,
            "session_name": None,
            "working_dir": None,
            "output": None,
            "prompt": "Do the thing",
            "children": [
                {"id": 11, "status": "completed", "subject": "Sub-task A", "assignee": "oppy"},
                {"id": 12, "status": "in_progress", "subject": "Sub-task B", "assignee": "jerry"},
            ],
        }
        tools = _make_tools(mock_mailbox)
        result = await tools["get_task"](10)
        assert "Task #10" in result
        assert "Parent task: #5" in result
        assert "Root task: #1" in result
        assert "Children (2):" in result
        assert "#11 [completed] Sub-task A" in result
        assert "#12 [in_progress] Sub-task B" in result

    @pytest.mark.asyncio
    async def test_shows_thrum_id(self):
        mock_mailbox = AsyncMock()
        mock_mailbox.get_task.return_value = {
            "id": 15,
            "status": "in_progress",
            "subject": "Thrum-linked task",
            "assignee": "oppy",
            "creator": "kamaji",
            "created_at": "2026-02-20T10:00:00Z",
            "completed_at": None,
            "parent_task_id": None,
            "root_task_id": None,
            "thrum_id": 3,
            "host": None,
            "session_name": None,
            "working_dir": None,
            "output": None,
            "prompt": "Work on thrum step",
            "children": [],
        }
        tools = _make_tools(mock_mailbox)
        result = await tools["get_task"](15)
        assert "Task #15" in result
        assert "Thrum: #3" in result
