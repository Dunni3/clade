"""Tests for Ember server authentication."""

import pytest
from unittest.mock import patch

from clade.worker.auth import get_api_key, verify_token

from fastapi import HTTPException


class TestGetApiKey:
    @patch.dict("os.environ", {"HEARTH_API_KEY": "test-key-123"})
    def test_returns_hearth_key(self):
        assert get_api_key() == "test-key-123"

    @patch.dict("os.environ", {"MAILBOX_API_KEY": "legacy-key"}, clear=True)
    def test_falls_back_to_mailbox_key(self):
        assert get_api_key() == "legacy-key"

    @patch.dict("os.environ", {"HEARTH_API_KEY": "hearth", "MAILBOX_API_KEY": "mailbox"})
    def test_hearth_takes_precedence(self):
        assert get_api_key() == "hearth"

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_without_env_var(self):
        with pytest.raises(RuntimeError, match="HEARTH_API_KEY"):
            get_api_key()

    @patch.dict("os.environ", {"HEARTH_API_KEY": ""})
    def test_raises_with_empty_key(self):
        with pytest.raises(RuntimeError, match="HEARTH_API_KEY"):
            get_api_key()


class TestVerifyToken:
    @patch.dict("os.environ", {"HEARTH_API_KEY": "secret-key"})
    @pytest.mark.asyncio
    async def test_valid_token(self):
        result = await verify_token("Bearer secret-key")
        assert result == "secret-key"

    @patch.dict("os.environ", {"HEARTH_API_KEY": "secret-key"})
    @pytest.mark.asyncio
    async def test_invalid_token(self):
        with pytest.raises(HTTPException) as exc_info:
            await verify_token("Bearer wrong-key")
        assert exc_info.value.status_code == 401

    @patch.dict("os.environ", {"HEARTH_API_KEY": "secret-key"})
    @pytest.mark.asyncio
    async def test_malformed_header_no_bearer(self):
        with pytest.raises(HTTPException) as exc_info:
            await verify_token("Basic secret-key")
        assert exc_info.value.status_code == 401

    @patch.dict("os.environ", {"HEARTH_API_KEY": "secret-key"})
    @pytest.mark.asyncio
    async def test_malformed_header_no_space(self):
        with pytest.raises(HTTPException) as exc_info:
            await verify_token("Bearersecret-key")
        assert exc_info.value.status_code == 401
