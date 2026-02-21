"""Configuration loaded from environment variables."""

import os

DB_PATH = os.environ.get("HEARTH_DB_PATH") or os.environ.get("MAILBOX_DB_PATH", "hearth.db")

# API keys: comma-separated list of "key:name" pairs
# e.g. "abc123:doot,def456:oppy,ghi789:jerry"
API_KEYS_RAW = os.environ.get("HEARTH_API_KEYS") or os.environ.get("MAILBOX_API_KEYS", "")


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

# Ember URLs: comma-separated "name=url" pairs for proxying health checks.
# e.g. "oppy=http://100.71.57.52:8100,jerry=http://100.99.1.2:8100"
EMBER_URLS_RAW = os.environ.get("EMBER_URLS", "")


def parse_ember_urls(raw: str) -> dict[str, str]:
    """Parse 'name=url,name=url,...' into {name: url} dict."""
    urls = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        name, url = entry.split("=", 1)
        urls[name.strip()] = url.strip()
    return urls


EMBER_URLS: dict[str, str] = parse_ember_urls(EMBER_URLS_RAW)
