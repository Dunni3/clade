"""Registry-first ember URL resolution.

The Hearth ember registry is the single source of truth for ember URLs.
clade.yaml (or in-memory config) is a degraded fallback used only when
the Hearth is unreachable or has no entry for a brother.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..communication.mailbox_client import MailboxClient

logger = logging.getLogger(__name__)


class EmberResolutionError(Exception):
    """Raised when no ember URL can be resolved from any source."""


@dataclass
class EmberResolution:
    """Result of resolving an ember URL for a brother."""

    url: str
    source: str  # "registry" or "config"
    warnings: list[str] = field(default_factory=list)


async def resolve_ember_url(
    brother: str,
    mailbox: MailboxClient | None,
    config_url: str | None = None,
) -> EmberResolution:
    """Resolve an ember URL using registry-first strategy.

    1. Query Hearth registry via ``GET /api/v1/embers/{name}`` → return URL if found.
    2. Fall back to *config_url* (from clade.yaml or in-memory registry) with a warning.
    3. Raise :class:`EmberResolutionError` if neither source yields a URL.

    When the registry hit succeeds and *config_url* differs, an informational
    drift warning is included in the result.

    Args:
        brother: Brother name (e.g. ``"jerry"``).
        mailbox: MailboxClient for Hearth API calls, or None if not configured.
        config_url: Ember URL from local config (clade.yaml / registry dict).

    Returns:
        :class:`EmberResolution` with the resolved URL and any warnings.

    Raises:
        EmberResolutionError: When neither the Hearth registry nor local config
            provides a URL.
    """
    warnings: list[str] = []

    # 1. Try Hearth registry
    if mailbox is not None:
        try:
            entry = await mailbox.get_ember(brother)
            if entry is not None:
                registry_url = entry["ember_url"]
                # Drift detection
                if config_url and config_url != registry_url:
                    warnings.append(
                        f"Config drift detected for {brother}: "
                        f"local config has {config_url}, "
                        f"registry has {registry_url}"
                    )
                    logger.info(
                        "Ember URL drift for %s: config=%s registry=%s",
                        brother,
                        config_url,
                        registry_url,
                    )
                return EmberResolution(
                    url=registry_url, source="registry", warnings=warnings
                )
        except Exception as exc:
            warnings.append(
                f"Could not reach Hearth registry for {brother}: {exc}. "
                "Falling back to local config — ember URL may be stale."
            )
            logger.warning(
                "Hearth registry lookup failed for %s: %s", brother, exc
            )

    # 2. Fall back to local config
    if config_url:
        warnings.append(
            f"Using local config URL for {brother} — "
            "Hearth registry was unavailable or returned no entry. "
            "URL may be stale for ephemeral workers."
        )
        return EmberResolution(url=config_url, source="config", warnings=warnings)

    # 3. Neither works
    raise EmberResolutionError(
        f"No ember URL found for '{brother}'. "
        "The Hearth registry has no entry and local config has no ember_host. "
        "Check: (1) Is the brother's Ember running? "
        "(2) Is the Hearth reachable? "
        "(3) Has the brother registered with the Hearth?"
    )
