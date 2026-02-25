"""Type definitions for Clade configuration."""

from typing import TypedDict, Optional


class BrotherConfig(TypedDict, total=False):
    """Configuration for a brother instance."""

    host: str
    working_dir: Optional[str]
    description: str
    projects: dict[str, str]


class MailboxConfig(TypedDict, total=False):
    """Configuration for mailbox connection."""

    url: str
    name: str
    # api_key is loaded from environment variable


class TerminalSpawnerConfig(TypedDict):
    """Complete configuration for the Clade."""

    brothers: dict[str, BrotherConfig]
    mailbox: Optional[MailboxConfig]
