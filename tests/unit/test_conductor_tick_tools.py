"""Unit tests for conductor ToolExecutor (Anthropic API tool dispatch)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from clade.conductor.tools import ToolExecutor

WORKER_REGISTRY = {
    "oppy": {
        "ember_url": "http://100.71.57.52:8100",
        "ember_api_key": "oppy-key",
        "hearth_api_key": "oppy-hearth-key",
        "working_dir": "~/projects/test",
    },
}


def _make_executor(mailbox=None, registry=None, **kwargs):
    mb = mailbox or AsyncMock()
    reg = registry if registry is not None else WORKER_REGISTRY
    return ToolExecutor(mb, reg, mailbox_name="kamaji", **kwargs)


class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        executor = _make_executor()
        result = await executor.execute("nonexistent_tool", {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_tool_exception_caught(self):
        executor = _make_executor()
        executor.mailbox.send_message = AsyncMock(side_effect=Exception("Network error"))
        result = await executor.execute("send_message", {"recipients": ["oppy"], "body": "hi"})
        assert "Error" in result


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.send_message.return_value = {"id": 42}
        executor = _make_executor(mb)
        result = await executor.execute("send_message", {
            "recipients": ["oppy", "jerry"],
            "body": "Hello brothers",
            "subject": "Greetings",
        })
        assert "Message sent" in result
        assert "42" in result
        assert "oppy, jerry" in result


class TestCheckMailbox:
    @pytest.mark.asyncio
    async def test_no_messages(self):
        mb = AsyncMock()
        mb.check_mailbox.return_value = []
        executor = _make_executor(mb)
        result = await executor.execute("check_mailbox", {})
        assert "No unread messages" in result

    @pytest.mark.asyncio
    async def test_with_messages(self):
        mb = AsyncMock()
        mb.check_mailbox.return_value = [
            {
                "id": 10,
                "sender": "oppy",
                "subject": "Status update",
                "body": "Task completed successfully",
                "is_read": False,
                "created_at": "2026-02-26T12:00:00Z",
            }
        ]
        executor = _make_executor(mb)
        result = await executor.execute("check_mailbox", {"unread_only": True})
        assert "#10" in result
        assert "[NEW]" in result
        assert "oppy" in result


class TestReadMessage:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.read_message.return_value = {
            "id": 5,
            "sender": "oppy",
            "recipients": ["kamaji"],
            "subject": "Done",
            "body": "Task finished.",
            "created_at": "2026-02-26T12:00:00Z",
            "read_by": [],
        }
        executor = _make_executor(mb)
        result = await executor.execute("read_message", {"message_id": 5})
        assert "Message #5" in result
        assert "oppy" in result
        assert "Task finished." in result


class TestListTasks:
    @pytest.mark.asyncio
    async def test_no_tasks(self):
        mb = AsyncMock()
        mb.get_tasks.return_value = []
        executor = _make_executor(mb)
        result = await executor.execute("list_tasks", {"status": "launched"})
        assert "No tasks found" in result

    @pytest.mark.asyncio
    async def test_with_tasks(self):
        mb = AsyncMock()
        mb.get_tasks.return_value = [
            {
                "id": 100,
                "status": "launched",
                "subject": "Build feature",
                "assignee": "oppy",
                "creator": "kamaji",
                "created_at": "2026-02-26T10:00:00Z",
                "completed_at": None,
                "blocked_by_task_id": None,
            }
        ]
        executor = _make_executor(mb)
        result = await executor.execute("list_tasks", {})
        assert "#100" in result
        assert "launched" in result
        assert "Build feature" in result


class TestGetTask:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.get_task.return_value = {
            "id": 50,
            "status": "completed",
            "subject": "Review code",
            "assignee": "oppy",
            "creator": "kamaji",
            "created_at": "2026-02-26T08:00:00Z",
            "completed_at": "2026-02-26T09:00:00Z",
            "parent_task_id": None,
            "root_task_id": 50,
            "blocked_by_task_id": None,
            "host": None,
            "session_name": None,
            "working_dir": None,
            "on_complete": None,
            "metadata": None,
            "output": "All tests pass",
            "prompt": "Review the PR",
            "linked_cards": [],
            "children": [],
            "blocked_tasks": [],
        }
        executor = _make_executor(mb)
        result = await executor.execute("get_task", {"task_id": 50})
        assert "Task #50" in result
        assert "completed" in result
        assert "All tests pass" in result


class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.update_task.return_value = {
            "id": 60,
            "status": "completed",
            "assignee": "oppy",
            "parent_task_id": 55,
            "root_task_id": 50,
        }
        executor = _make_executor(mb)
        result = await executor.execute("update_task", {
            "task_id": 60,
            "status": "completed",
            "output": "Done",
        })
        assert "Task #60 updated" in result
        assert "completed" in result


class TestRetryTask:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.retry_task.return_value = {
            "id": 70,
            "subject": "Retry: Build feature",
            "status": "pending",
            "assignee": "oppy",
            "parent_task_id": 65,
        }
        executor = _make_executor(mb)
        result = await executor.execute("retry_task", {"task_id": 65})
        assert "Retry task #70" in result
        assert "pending" in result


class TestKillTask:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.kill_task.return_value = {
            "id": 80,
            "status": "killed",
            "assignee": "oppy",
        }
        executor = _make_executor(mb)
        result = await executor.execute("kill_task", {"task_id": 80})
        assert "Task #80 killed" in result
        assert "killed" in result


class TestDepositMorsel:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.create_morsel.return_value = {"id": 500}
        executor = _make_executor(mb)
        result = await executor.execute("deposit_morsel", {
            "body": "Tick completed. All quiet.",
            "tags": ["conductor-tick"],
        })
        assert "Morsel #500 deposited" in result
        mb.create_morsel.assert_called_once()
        call_kwargs = mb.create_morsel.call_args.kwargs
        assert call_kwargs["body"] == "Tick completed. All quiet."
        assert call_kwargs["tags"] == ["conductor-tick"]

    @pytest.mark.asyncio
    async def test_with_links(self):
        mb = AsyncMock()
        mb.create_morsel.return_value = {"id": 501}
        executor = _make_executor(mb)
        result = await executor.execute("deposit_morsel", {
            "body": "Task completed",
            "task_id": 42,
            "card_id": 10,
        })
        assert "Morsel #501" in result
        call_kwargs = mb.create_morsel.call_args.kwargs
        links = call_kwargs["links"]
        assert {"object_type": "task", "object_id": "42"} in links
        assert {"object_type": "card", "object_id": "10"} in links


class TestDelegateTask:
    @pytest.mark.asyncio
    async def test_unknown_worker(self):
        executor = _make_executor()
        result = await executor.execute("delegate_task", {
            "brother": "unknown",
            "prompt": "Do stuff",
        })
        assert "Unknown worker" in result

    @pytest.mark.asyncio
    async def test_no_ember(self):
        registry = {"oppy": {"working_dir": "~/test"}}
        executor = _make_executor(registry=registry)
        result = await executor.execute("delegate_task", {
            "brother": "oppy",
            "prompt": "Do stuff",
        })
        assert "no Ember configured" in result

    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.create_task.return_value = {"id": 90}
        mb.update_task.return_value = {"id": 90, "status": "launched"}

        executor = _make_executor(mb)

        with pytest.MonkeyPatch.context() as mp:
            from clade.conductor import tools as tools_module
            mock_execute = AsyncMock(
                return_value={"session_name": "task-oppy-test-123", "message": "ok"}
            )

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass
                async def execute_task(self, **kwargs):
                    return await mock_execute(**kwargs)

            mp.setattr(tools_module, "EmberClient", MockEmberClient)

            result = await executor.execute("delegate_task", {
                "brother": "oppy",
                "prompt": "Review code",
                "subject": "Code review",
            })

        assert "Task #90" in result
        assert "delegated to oppy" in result
        assert "launched" in result

    @pytest.mark.asyncio
    async def test_blocked_task(self):
        mb = AsyncMock()
        mb.create_task.return_value = {"id": 91, "blocked_by_task_id": 88}
        executor = _make_executor(mb)

        result = await executor.execute("delegate_task", {
            "brother": "oppy",
            "prompt": "Review after build",
            "blocked_by_task_id": 88,
        })

        assert "Task #91" in result
        assert "deferred" in result
        assert "blocked by #88" in result


class TestCheckWorkerHealth:
    @pytest.mark.asyncio
    async def test_no_workers(self):
        executor = _make_executor(registry={})
        result = await executor.execute("check_worker_health", {})
        assert "No workers configured" in result

    @pytest.mark.asyncio
    async def test_healthy(self):
        executor = _make_executor()
        with pytest.MonkeyPatch.context() as mp:
            from clade.conductor import tools as tools_module

            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    pass
                async def health(self):
                    return {"active_tasks": 1, "uptime_seconds": 3600}

            mp.setattr(tools_module, "EmberClient", MockEmberClient)
            result = await executor.execute("check_worker_health", {})

        assert "Healthy" in result
        assert "oppy" in result


class TestListBoard:
    @pytest.mark.asyncio
    async def test_empty(self):
        mb = AsyncMock()
        mb.get_cards.return_value = []
        executor = _make_executor(mb)
        result = await executor.execute("list_board", {})
        assert "No cards found" in result

    @pytest.mark.asyncio
    async def test_with_cards(self):
        mb = AsyncMock()
        mb.get_cards.return_value = [
            {
                "id": 1,
                "title": "Build feature",
                "col": "in_progress",
                "priority": "high",
                "assignee": "oppy",
                "labels": ["dev"],
            }
        ]
        executor = _make_executor(mb)
        result = await executor.execute("list_board", {})
        assert "IN PROGRESS" in result
        assert "Build feature" in result
        assert "[high]" in result


class TestCreateCard:
    @pytest.mark.asyncio
    async def test_success(self):
        mb = AsyncMock()
        mb.create_card.return_value = {"id": 99, "title": "New card", "col": "backlog"}
        executor = _make_executor(mb)
        result = await executor.execute("create_card", {"title": "New card"})
        assert "Card #99 created" in result

    @pytest.mark.asyncio
    async def test_invalid_column(self):
        executor = _make_executor()
        result = await executor.execute("create_card", {"title": "X", "col": "invalid"})
        assert "Invalid column" in result


class TestSearch:
    @pytest.mark.asyncio
    async def test_no_results(self):
        mb = AsyncMock()
        mb.search.return_value = {"results": []}
        executor = _make_executor(mb)
        result = await executor.execute("search", {"query": "nonexistent"})
        assert "No results" in result

    @pytest.mark.asyncio
    async def test_with_results(self):
        mb = AsyncMock()
        mb.search.return_value = {
            "results": [
                {
                    "type": "task",
                    "id": 42,
                    "title": "Build feature",
                    "snippet": "Build the <mark>feature</mark>",
                    "status": "completed",
                    "assignee": "oppy",
                    "creator": "kamaji",
                }
            ]
        }
        executor = _make_executor(mb)
        result = await executor.execute("search", {"query": "feature"})
        assert "[T] #42" in result
        assert "Build feature" in result
