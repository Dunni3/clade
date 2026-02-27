"""Anthropic API-based conductor agent.

Implements a simple tool-call loop using the Anthropic Python SDK.
Each tick is stateless — a fresh messages list per invocation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import Message, ContentBlock, ToolUseBlock, TextBlock

from .schemas import TOOLS
from .tools import ToolExecutor

logger = logging.getLogger(__name__)

# Default model for conductor ticks (cost-efficient for routine orchestration)
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Safety limit to prevent runaway loops
MAX_TURNS = 50


@dataclass
class TickResult:
    """Result of a conductor tick."""
    turns: int = 0
    tool_calls: int = 0
    final_text: str = ""
    error: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


async def run_tick(
    system_prompt: str,
    user_message: str,
    tool_executor: ToolExecutor,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    max_turns: int = MAX_TURNS,
    api_key: str | None = None,
) -> TickResult:
    """Run a single conductor tick using the Anthropic API.

    Args:
        system_prompt: The conductor system prompt (from conductor-tick.md).
        user_message: The assembled tick context message.
        tool_executor: ToolExecutor instance for dispatching tool calls.
        model: Model ID to use.
        max_tokens: Maximum tokens per response.
        max_turns: Maximum number of API round-trips before stopping.
        api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.

    Returns:
        TickResult with summary of what happened.
    """
    client = AsyncAnthropic(api_key=api_key)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message},
    ]
    result = TickResult()

    for turn in range(max_turns):
        result.turns = turn + 1
        logger.info("Conductor tick turn %d/%d", turn + 1, max_turns)

        try:
            response: Message = await client.messages.create(
                model=model,
                system=system_prompt,
                messages=messages,
                tools=TOOLS,
                max_tokens=max_tokens,
            )
        except Exception as e:
            result.error = f"API call failed on turn {turn + 1}: {e}"
            logger.error(result.error)
            break

        # Collect text and tool_use blocks
        assistant_content = response.content
        text_parts = []
        tool_uses: list[ToolUseBlock] = []

        for block in assistant_content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # Append assistant message to conversation
        # Convert content blocks to serializable dicts for the messages list
        messages.append({
            "role": "assistant",
            "content": _serialize_content(assistant_content),
        })

        # If no tool use, we're done
        if response.stop_reason == "end_turn" or not tool_uses:
            result.final_text = "\n".join(text_parts)
            break

        # Execute tool calls
        tool_results = []
        for tool_use in tool_uses:
            result.tool_calls += 1
            logger.info("Executing tool: %s", tool_use.name)
            try:
                tool_output = await tool_executor.execute(tool_use.name, tool_use.input)
            except Exception as e:
                tool_output = f"Tool execution error: {e}"
                logger.exception("Tool '%s' failed", tool_use.name)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": tool_output,
            })

        # Append tool results
        messages.append({"role": "user", "content": tool_results})

    else:
        # Exhausted max_turns
        result.error = f"Reached maximum turns ({max_turns}) without completing"
        logger.warning(result.error)

    result.messages = messages
    return result


def _serialize_content(content: list[ContentBlock]) -> list[dict]:
    """Convert Anthropic ContentBlock objects to serializable dicts."""
    serialized = []
    for block in content:
        if block.type == "text":
            serialized.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            serialized.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
        else:
            # Preserve unknown block types as-is
            serialized.append(block.model_dump() if hasattr(block, "model_dump") else {"type": block.type})
    return serialized
