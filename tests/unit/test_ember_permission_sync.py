"""Unit tests for Ember permission_flags fetch-and-cache logic (card #88)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set env vars before importing ember module
os.environ.setdefault("EMBER_BROTHER_NAME", "oppy")


class TestFetchPermissionsFromHearth:
    """Tests for _fetch_permissions_from_hearth()."""

    @pytest.mark.asyncio
    async def test_returns_permission_flags_on_success(self):
        """Successfully fetches permission_flags from Hearth."""
        from clade.worker.ember import _fetch_permissions_from_hearth

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"name": "oppy", "permission_flags": "--dangerously-skip-permissions"}

        with patch("clade.worker.ember._hearth_url", "http://hearth:8080"), \
             patch("clade.worker.ember._hearth_api_key", "test-key"), \
             patch("clade.worker.ember.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _fetch_permissions_from_hearth()

        assert result == "--dangerously-skip-permissions"

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_not_registered(self):
        """Returns '' when ember is not registered in Hearth (404)."""
        from clade.worker.ember import _fetch_permissions_from_hearth

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("clade.worker.ember._hearth_url", "http://hearth:8080"), \
             patch("clade.worker.ember._hearth_api_key", "test-key"), \
             patch("clade.worker.ember.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _fetch_permissions_from_hearth()

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self):
        """Returns None when Hearth is unreachable."""
        from clade.worker.ember import _fetch_permissions_from_hearth

        with patch("clade.worker.ember._hearth_url", "http://hearth:8080"), \
             patch("clade.worker.ember._hearth_api_key", "test-key"), \
             patch("clade.worker.ember.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = Exception("Connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _fetch_permissions_from_hearth()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_hearth_configured(self):
        """Returns None when HEARTH_URL is not set."""
        from clade.worker.ember import _fetch_permissions_from_hearth

        with patch("clade.worker.ember._hearth_url", None), \
             patch("clade.worker.ember._hearth_api_key", None):
            result = await _fetch_permissions_from_hearth()

        assert result is None


class TestPermissionsCache:
    """Tests for local permissions cache read/write."""

    def test_write_and_read_cache(self, tmp_path):
        """Write flags to cache and read them back."""
        from clade.worker.ember import _write_permissions_cache, _read_permissions_cache

        cache_file = tmp_path / "ember_permissions_cache.txt"
        with patch("clade.worker.ember._permissions_cache_path", cache_file):
            _write_permissions_cache("--dangerously-skip-permissions")
            result = _read_permissions_cache()

        assert result == "--dangerously-skip-permissions"

    def test_read_missing_cache_returns_empty(self, tmp_path):
        """Returns '' when cache file does not exist."""
        from clade.worker.ember import _read_permissions_cache

        nonexistent = tmp_path / "no_such_file.txt"
        with patch("clade.worker.ember._permissions_cache_path", nonexistent):
            result = _read_permissions_cache()

        assert result == ""

    def test_write_cache_creates_parent_dirs(self, tmp_path):
        """Cache write creates parent directories if needed."""
        from clade.worker.ember import _write_permissions_cache, _read_permissions_cache

        deep_cache = tmp_path / "a" / "b" / "cache.txt"
        with patch("clade.worker.ember._permissions_cache_path", deep_cache):
            _write_permissions_cache("--permission-mode acceptEdits")
            result = _read_permissions_cache()

        assert result == "--permission-mode acceptEdits"


class TestGetPermissionFlags:
    """Tests for the get_permission_flags() high-level function."""

    @pytest.mark.asyncio
    async def test_uses_hearth_flags_and_caches(self, tmp_path):
        """Fetches from Hearth, caches result, returns flags."""
        from clade.worker.ember import get_permission_flags, _read_permissions_cache

        cache_file = tmp_path / "cache.txt"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"permission_flags": "--dangerously-skip-permissions"}

        with patch("clade.worker.ember._hearth_url", "http://hearth:8080"), \
             patch("clade.worker.ember._hearth_api_key", "test-key"), \
             patch("clade.worker.ember._permissions_cache_path", cache_file), \
             patch("clade.worker.ember.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_permission_flags()

        assert result == "--dangerously-skip-permissions"
        # Also written to cache
        with patch("clade.worker.ember._permissions_cache_path", cache_file):
            cached = _read_permissions_cache()
        assert cached == "--dangerously-skip-permissions"

    @pytest.mark.asyncio
    async def test_falls_back_to_cache_when_hearth_unreachable(self, tmp_path):
        """When Hearth is unreachable, returns cached value."""
        from clade.worker.ember import get_permission_flags, _write_permissions_cache

        cache_file = tmp_path / "cache.txt"
        with patch("clade.worker.ember._permissions_cache_path", cache_file):
            _write_permissions_cache("--dangerously-skip-permissions")

        with patch("clade.worker.ember._hearth_url", "http://hearth:8080"), \
             patch("clade.worker.ember._hearth_api_key", "test-key"), \
             patch("clade.worker.ember._permissions_cache_path", cache_file), \
             patch("clade.worker.ember.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = Exception("Unreachable")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_permission_flags()

        assert result == "--dangerously-skip-permissions"

    @pytest.mark.asyncio
    async def test_returns_empty_when_both_unavailable(self, tmp_path):
        """Returns '' when both Hearth and cache are unavailable."""
        from clade.worker.ember import get_permission_flags

        nonexistent = tmp_path / "no_cache.txt"
        with patch("clade.worker.ember._hearth_url", None), \
             patch("clade.worker.ember._hearth_api_key", None), \
             patch("clade.worker.ember._permissions_cache_path", nonexistent):
            result = await get_permission_flags()

        assert result == ""
