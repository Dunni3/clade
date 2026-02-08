"""Type definitions for terminal-spawner configuration."""

from typing import TypedDict, Optional


class BrotherConfig(TypedDict):
    """Configuration for a brother instance."""

    host: str
    working_dir: Optional[str]
    command: str
    description: str


class MailboxConfig(TypedDict, total=False):
    """Configuration for mailbox connection."""

    url: str
    name: str
    # api_key is loaded from environment variable


class TerminalSpawnerConfig(TypedDict):
    """Complete configuration for terminal-spawner."""

    default_terminal_app: str
    brothers: dict[str, BrotherConfig]
    mailbox: Optional[MailboxConfig]
