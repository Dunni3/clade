"""Tests for registry-first ember URL resolution."""

from unittest.mock import AsyncMock

import pytest

from clade.worker.resolver import (
    EmberResolution,
    EmberResolutionError,
    resolve_ember_url,
)


class TestResolveEmberUrl:
    """Tests for resolve_ember_url()."""

    @pytest.mark.asyncio
    async def test_registry_hit(self):
        """Registry URL is returned when available."""
        mailbox = AsyncMock()
        mailbox.get_ember.return_value = {
            "name": "jerry",
            "ember_url": "http://100.99.0.1:8100",
        }

        result = await resolve_ember_url("jerry", mailbox, config_url=None)

        assert result.url == "http://100.99.0.1:8100"
        assert result.source == "registry"
        assert not result.warnings
        mailbox.get_ember.assert_awaited_once_with("jerry")

    @pytest.mark.asyncio
    async def test_registry_hit_with_matching_config(self):
        """No drift warning when registry and config URLs match."""
        mailbox = AsyncMock()
        mailbox.get_ember.return_value = {
            "name": "oppy",
            "ember_url": "http://100.71.57.52:8100",
        }

        result = await resolve_ember_url(
            "oppy", mailbox, config_url="http://100.71.57.52:8100"
        )

        assert result.url == "http://100.71.57.52:8100"
        assert result.source == "registry"
        assert not result.warnings

    @pytest.mark.asyncio
    async def test_registry_hit_with_drift(self):
        """Drift warning when registry URL differs from config URL."""
        mailbox = AsyncMock()
        mailbox.get_ember.return_value = {
            "name": "jerry",
            "ember_url": "http://100.99.0.NEW:8100",
        }

        result = await resolve_ember_url(
            "jerry", mailbox, config_url="http://100.99.0.OLD:8100"
        )

        assert result.url == "http://100.99.0.NEW:8100"
        assert result.source == "registry"
        assert len(result.warnings) == 1
        assert "drift" in result.warnings[0].lower()
        assert "100.99.0.OLD" in result.warnings[0]
        assert "100.99.0.NEW" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_registry_not_found_falls_back_to_config(self):
        """Falls back to config URL when registry has no entry."""
        mailbox = AsyncMock()
        mailbox.get_ember.return_value = None

        result = await resolve_ember_url(
            "jerry", mailbox, config_url="http://10.0.0.5:8100"
        )

        assert result.url == "http://10.0.0.5:8100"
        assert result.source == "config"
        assert len(result.warnings) == 1
        assert "local config" in result.warnings[0].lower()

    @pytest.mark.asyncio
    async def test_registry_error_falls_back_to_config(self):
        """Falls back to config URL when registry lookup fails."""
        mailbox = AsyncMock()
        mailbox.get_ember.side_effect = Exception("connection refused")

        result = await resolve_ember_url(
            "jerry", mailbox, config_url="http://10.0.0.5:8100"
        )

        assert result.url == "http://10.0.0.5:8100"
        assert result.source == "config"
        assert len(result.warnings) == 2
        assert "could not reach" in result.warnings[0].lower()
        assert "local config" in result.warnings[1].lower()

    @pytest.mark.asyncio
    async def test_no_mailbox_falls_back_to_config(self):
        """Falls back to config URL when no mailbox is available."""
        result = await resolve_ember_url(
            "jerry", mailbox=None, config_url="http://10.0.0.5:8100"
        )

        assert result.url == "http://10.0.0.5:8100"
        assert result.source == "config"
        assert len(result.warnings) == 1

    @pytest.mark.asyncio
    async def test_both_fail_raises_error(self):
        """Raises EmberResolutionError when neither registry nor config works."""
        mailbox = AsyncMock()
        mailbox.get_ember.return_value = None

        with pytest.raises(EmberResolutionError) as exc_info:
            await resolve_ember_url("jerry", mailbox, config_url=None)

        assert "jerry" in str(exc_info.value)
        assert "Hearth" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_mailbox_no_config_raises_error(self):
        """Raises EmberResolutionError with no mailbox and no config URL."""
        with pytest.raises(EmberResolutionError):
            await resolve_ember_url("jerry", mailbox=None, config_url=None)

    @pytest.mark.asyncio
    async def test_registry_error_no_config_raises_error(self):
        """Raises EmberResolutionError when registry fails and no config fallback."""
        mailbox = AsyncMock()
        mailbox.get_ember.side_effect = Exception("timeout")

        with pytest.raises(EmberResolutionError):
            await resolve_ember_url("jerry", mailbox, config_url=None)
