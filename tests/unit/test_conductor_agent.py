"""Unit tests for the Anthropic API conductor agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clade.conductor.agent import TickResult, run_tick, _serialize_content
from clade.conductor.tools import ToolExecutor


def _make_tool_executor(mailbox=None, registry=None):
    """Create a ToolExecutor with mock clients."""
    mb = mailbox or AsyncMock()
    reg = registry or {}
    return ToolExecutor(mb, reg, mailbox_name="kamaji")


def _mock_message(content_blocks, stop_reason="end_turn"):
    """Create a mock Anthropic Message response."""
    msg = MagicMock()
    msg.content = content_blocks
    msg.stop_reason = stop_reason
    return msg


def _text_block(text: str):
    """Create a mock TextBlock."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(tool_id: str, name: str, tool_input: dict):
    """Create a mock ToolUseBlock."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = tool_input
    return block


class TestRunTick:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """Agent returns text with no tool calls — single turn."""
        executor = _make_tool_executor()
        mock_response = _mock_message([_text_block("All quiet. Nothing to do.")])

        with patch("clade.conductor.agent.AsyncAnthropic") as MockClient:
            instance = AsyncMock()
            instance.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = instance

            result = await run_tick(
                system_prompt="You are Kamaji.",
                user_message="Periodic tick.",
                tool_executor=executor,
                api_key="test-key",
            )

        assert result.turns == 1
        assert result.tool_calls == 0
        assert result.error is None
        assert "All quiet" in result.final_text

    @pytest.mark.asyncio
    async def test_tool_call_then_response(self):
        """Agent makes a tool call, gets result, then responds with text."""
        executor = _make_tool_executor()
        # Mock the executor to return a known result
        executor.execute = AsyncMock(return_value="No unread messages.")

        # First call: tool use
        tool_block = _tool_use_block("tu_1", "check_mailbox", {"unread_only": True})
        response1 = _mock_message([tool_block], stop_reason="tool_use")

        # Second call: final text
        response2 = _mock_message([_text_block("Checked mailbox. All clear.")], stop_reason="end_turn")

        with patch("clade.conductor.agent.AsyncAnthropic") as MockClient:
            instance = AsyncMock()
            instance.messages.create = AsyncMock(side_effect=[response1, response2])
            MockClient.return_value = instance

            result = await run_tick(
                system_prompt="You are Kamaji.",
                user_message="Periodic tick.",
                tool_executor=executor,
                api_key="test-key",
            )

        assert result.turns == 2
        assert result.tool_calls == 1
        assert result.error is None
        assert "All clear" in result.final_text
        executor.execute.assert_called_once_with("check_mailbox", {"unread_only": True})

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_response(self):
        """Agent makes multiple tool calls in a single response."""
        executor = _make_tool_executor()
        executor.execute = AsyncMock(side_effect=["No unread messages.", "2 tasks found."])

        # First call: two tool uses
        tool1 = _tool_use_block("tu_1", "check_mailbox", {})
        tool2 = _tool_use_block("tu_2", "list_tasks", {"status": "launched"})
        response1 = _mock_message([tool1, tool2], stop_reason="tool_use")

        # Second call: final text
        response2 = _mock_message([_text_block("Done.")], stop_reason="end_turn")

        with patch("clade.conductor.agent.AsyncAnthropic") as MockClient:
            instance = AsyncMock()
            instance.messages.create = AsyncMock(side_effect=[response1, response2])
            MockClient.return_value = instance

            result = await run_tick(
                system_prompt="You are Kamaji.",
                user_message="Periodic tick.",
                tool_executor=executor,
                api_key="test-key",
            )

        assert result.turns == 2
        assert result.tool_calls == 2

    @pytest.mark.asyncio
    async def test_max_turns_limit(self):
        """Agent hits max turns limit."""
        executor = _make_tool_executor()
        executor.execute = AsyncMock(return_value="result")

        # Every response is a tool call
        tool_block = _tool_use_block("tu_loop", "check_mailbox", {})
        looping_response = _mock_message([tool_block], stop_reason="tool_use")

        with patch("clade.conductor.agent.AsyncAnthropic") as MockClient:
            instance = AsyncMock()
            instance.messages.create = AsyncMock(return_value=looping_response)
            MockClient.return_value = instance

            result = await run_tick(
                system_prompt="You are Kamaji.",
                user_message="Periodic tick.",
                tool_executor=executor,
                api_key="test-key",
                max_turns=3,
            )

        assert result.turns == 3
        assert result.error is not None
        assert "maximum turns" in result.error.lower()

    @pytest.mark.asyncio
    async def test_api_error(self):
        """API call failure is handled gracefully."""
        executor = _make_tool_executor()

        with patch("clade.conductor.agent.AsyncAnthropic") as MockClient:
            instance = AsyncMock()
            instance.messages.create = AsyncMock(side_effect=Exception("Rate limited"))
            MockClient.return_value = instance

            result = await run_tick(
                system_prompt="You are Kamaji.",
                user_message="Periodic tick.",
                tool_executor=executor,
                api_key="test-key",
            )

        assert result.turns == 1
        assert result.error is not None
        assert "Rate limited" in result.error

    @pytest.mark.asyncio
    async def test_tool_error_doesnt_crash(self):
        """Tool execution error is caught and returned as tool result."""
        executor = _make_tool_executor()
        executor.execute = AsyncMock(side_effect=Exception("Connection refused"))

        tool_block = _tool_use_block("tu_err", "check_worker_health", {})
        response1 = _mock_message([tool_block], stop_reason="tool_use")
        response2 = _mock_message([_text_block("Worker unreachable.")], stop_reason="end_turn")

        with patch("clade.conductor.agent.AsyncAnthropic") as MockClient:
            instance = AsyncMock()
            instance.messages.create = AsyncMock(side_effect=[response1, response2])
            MockClient.return_value = instance

            result = await run_tick(
                system_prompt="You are Kamaji.",
                user_message="Periodic tick.",
                tool_executor=executor,
                api_key="test-key",
            )

        assert result.turns == 2
        assert result.tool_calls == 1
        assert result.error is None  # Agent recovered

    @pytest.mark.asyncio
    async def test_messages_list_built_correctly(self):
        """Verify the messages list is built with proper structure."""
        executor = _make_tool_executor()
        executor.execute = AsyncMock(return_value="No messages.")

        tool_block = _tool_use_block("tu_1", "check_mailbox", {})
        response1 = _mock_message([tool_block], stop_reason="tool_use")
        response2 = _mock_message([_text_block("Done.")], stop_reason="end_turn")

        with patch("clade.conductor.agent.AsyncAnthropic") as MockClient:
            instance = AsyncMock()
            instance.messages.create = AsyncMock(side_effect=[response1, response2])
            MockClient.return_value = instance

            result = await run_tick(
                system_prompt="System prompt",
                user_message="User message",
                tool_executor=executor,
                api_key="test-key",
            )

        # Messages should be: user, assistant (tool_use), user (tool_result), assistant (text)
        assert len(result.messages) == 4
        assert result.messages[0]["role"] == "user"
        assert result.messages[0]["content"] == "User message"
        assert result.messages[1]["role"] == "assistant"
        assert result.messages[2]["role"] == "user"
        assert result.messages[2]["content"][0]["type"] == "tool_result"
        assert result.messages[3]["role"] == "assistant"


class TestSerializeContent:
    def test_text_block(self):
        block = _text_block("hello")
        result = _serialize_content([block])
        assert result == [{"type": "text", "text": "hello"}]

    def test_tool_use_block(self):
        block = _tool_use_block("tu_1", "check_mailbox", {"limit": 5})
        result = _serialize_content([block])
        assert result == [{"type": "tool_use", "id": "tu_1", "name": "check_mailbox", "input": {"limit": 5}}]

    def test_mixed_blocks(self):
        text = _text_block("thinking...")
        tool = _tool_use_block("tu_2", "list_tasks", {})
        result = _serialize_content([text, tool])
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "tool_use"
