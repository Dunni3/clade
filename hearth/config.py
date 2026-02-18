"""Configuration loaded from environment variables."""

import os

DB_PATH = os.environ.get("MAILBOX_DB_PATH", "mailbox.db")

# API keys: comma-separated list of "key:name" pairs
# e.g. "abc123:doot,def456:oppy,ghi789:jerry"
API_KEYS_RAW = os.environ.get("MAILBOX_API_KEYS", "")


def parse_api_keys(raw: str) -> dict[str, str]:
    """Parse 'key:name,key:name,...' into {key: name} dict."""
    keys = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        key, name = entry.split(":", 1)
        keys[key.strip()] = name.strip()
    return keys


API_KEYS: dict[str, str] = parse_api_keys(API_KEYS_RAW)

# Shell command to trigger a conductor tick (fire-and-forget).
# None = disabled (no-op). Set to e.g. "bash /path/to/conductor-tick.sh" to enable.
CONDUCTOR_TICK_CMD: str | None = os.environ.get("CONDUCTOR_TICK_CMD")
