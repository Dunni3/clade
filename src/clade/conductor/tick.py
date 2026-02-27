"""Entry point for Anthropic API-based conductor ticks.

Usage:
    python -m clade.conductor.tick          # periodic tick
    TRIGGER_TASK_ID=42 python -m clade.conductor.tick   # event-driven
    TRIGGER_MESSAGE_ID=7 python -m clade.conductor.tick # message-driven

Environment variables:
    ANTHROPIC_API_KEY     — Required. Anthropic API key.
    HEARTH_URL            — Required. Hearth server URL.
    HEARTH_API_KEY        — Required. API key for Hearth.
    HEARTH_NAME           — Conductor's identity name (default: "kamaji").
    CONDUCTOR_WORKERS_CONFIG — Path to conductor-workers.yaml.
    CONDUCTOR_TICK_PROMPT — Path to conductor-tick.md (optional override).
    CONDUCTOR_MODEL       — Model to use (default: claude-haiku-4-5-20251001).
    TRIGGER_TASK_ID       — If set, event-driven tick for this task.
    TRIGGER_MESSAGE_ID    — If set, message-driven tick for this message.
    KEYS_FILE             — Optional path to keys.json for worker API keys.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml

from ..cli.keys import load_keys, merge_keys_into_registry
from ..communication.mailbox_client import MailboxClient
from .agent import DEFAULT_MODEL, TickResult, run_tick
from .context import build_user_message, load_system_prompt
from .tools import ToolExecutor

logger = logging.getLogger(__name__)


def _load_worker_registry() -> dict[str, dict]:
    """Load worker registry from CONDUCTOR_WORKERS_CONFIG yaml."""
    config_path = os.environ.get("CONDUCTOR_WORKERS_CONFIG")
    if not config_path or not os.path.exists(config_path):
        return {}

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    registry = data.get("workers", {})

    # Interpolate env vars in string values (e.g. ${OPPY_HEARTH_API_KEY})
    for _worker_name, worker_config in registry.items():
        for key, value in worker_config.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                worker_config[key] = os.environ.get(env_var, value)

    # Merge keys from keys.json if available
    keys_file = os.environ.get("KEYS_FILE")
    if keys_file and os.path.exists(keys_file):
        all_keys = load_keys(Path(keys_file))
        merge_keys_into_registry(registry, all_keys)

    return registry


def _validate_env() -> tuple[str, str, str]:
    """Validate required environment variables.

    Returns:
        (hearth_url, hearth_api_key, hearth_name)

    Raises:
        SystemExit if required vars are missing.
    """
    hearth_url = os.environ.get("HEARTH_URL") or os.environ.get("MAILBOX_URL")
    hearth_api_key = os.environ.get("HEARTH_API_KEY") or os.environ.get("MAILBOX_API_KEY")
    hearth_name = os.environ.get("HEARTH_NAME") or os.environ.get("MAILBOX_NAME") or "kamaji"

    missing = []
    if not hearth_url:
        missing.append("HEARTH_URL")
    if not hearth_api_key:
        missing.append("HEARTH_API_KEY")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return hearth_url, hearth_api_key, hearth_name


async def async_main() -> TickResult:
    """Run a single conductor tick."""
    hearth_url, hearth_api_key, hearth_name = _validate_env()

    # Build components
    mailbox = MailboxClient(hearth_url, hearth_api_key, verify_ssl=False)
    worker_registry = _load_worker_registry()
    tool_executor = ToolExecutor(mailbox, worker_registry, mailbox_name=hearth_name)

    # Load prompt and context
    system_prompt = load_system_prompt()
    user_message = build_user_message()

    model = os.environ.get("CONDUCTOR_MODEL", DEFAULT_MODEL)

    logger.info("Starting conductor tick (model=%s)", model)

    result = await run_tick(
        system_prompt=system_prompt,
        user_message=user_message,
        tool_executor=tool_executor,
        model=model,
    )

    # Log outcome
    if result.error:
        logger.error("Tick finished with error: %s", result.error)
        print(f"Tick error: {result.error}", file=sys.stderr)
    else:
        logger.info(
            "Tick completed: %d turns, %d tool calls",
            result.turns,
            result.tool_calls,
        )

    if result.final_text:
        print(result.final_text)

    return result


def main():
    """Synchronous entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    result = asyncio.run(async_main())
    if result.error:
        sys.exit(1)
