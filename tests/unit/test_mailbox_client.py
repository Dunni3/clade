"""Unit tests for the MailboxClient HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clade.communication.mailbox_client import MailboxClient


class TestMailboxClient:
    def setup_method(self):
        self.client = MailboxClient("http://localhost:8000", "test-key")

    def _make_mock_resp(self, json_data):
        """Create a mock httpx Response with sync .json() and .raise_for_status()."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def _make_async_client(self, get_resp=None, post_resp=None):
        """Create a mock AsyncClient context manager."""
        instance = AsyncMock()
        if get_resp is not None:
            instance.get.return_value = get_resp
        if post_resp is not None:
            instance.post.return_value = post_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        return instance

    @pytest.mark.asyncio
    async def test_send_message(self):
        mock_resp = self._make_mock_resp({"id": 1, "message": "Message sent"})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.send_message(["oppy"], "Hello", "Test")
            assert result["id"] == 1
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_mailbox(self):
        mock_resp = self._make_mock_resp([
            {"id": 1, "sender": "doot", "subject": "Hi", "body": "Hello", "created_at": "2026-02-07T00:00:00Z", "is_read": False}
        ])

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.check_mailbox()
            assert len(result) == 1
            assert result[0]["sender"] == "doot"

    @pytest.mark.asyncio
    async def test_read_message(self):
        mock_get_resp = self._make_mock_resp({
            "id": 1, "sender": "doot", "subject": "Hi", "body": "Hello",
            "created_at": "2026-02-07T00:00:00Z", "recipients": ["oppy"], "is_read": False
        })
        mock_post_resp = self._make_mock_resp({"message": "Marked as read"})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_get_resp, post_resp=mock_post_resp)
            MockClient.return_value = instance

            result = await self.client.read_message(1)
            assert result["id"] == 1
            # Should also call post to mark as read
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_unread_count(self):
        mock_resp = self._make_mock_resp({"unread": 3})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.unread_count()
            assert result == 3

    def test_url_construction(self):
        c = MailboxClient("http://example.com/", "key")
        assert c._url("/messages") == "http://example.com/api/v1/messages"

    def test_url_no_trailing_slash(self):
        c = MailboxClient("http://example.com", "key")
        assert c._url("/messages") == "http://example.com/api/v1/messages"

    def test_auth_header(self):
        c = MailboxClient("http://example.com", "my-secret-key")
        assert c.headers["Authorization"] == "Bearer my-secret-key"
