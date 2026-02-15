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

    def test_register_key_sync_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        with patch("clade.communication.mailbox_client.httpx.post", return_value=mock_resp) as mock_post:
            result = self.client.register_key_sync("curie", "new-key-123")
            assert result is True
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert call_kwargs.kwargs["json"] == {"name": "curie", "key": "new-key-123"}

    def test_register_key_sync_conflict(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 409
        with patch("clade.communication.mailbox_client.httpx.post", return_value=mock_resp):
            result = self.client.register_key_sync("curie", "new-key-123")
            assert result is True  # 409 is OK — already registered

    def test_register_key_sync_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("clade.communication.mailbox_client.httpx.post", return_value=mock_resp):
            result = self.client.register_key_sync("curie", "new-key-123")
            assert result is False

    @pytest.mark.asyncio
    async def test_create_thrum(self):
        mock_resp = self._make_mock_resp({"id": 1, "message": "Thrum created"})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.create_thrum(
                title="Test", goal="Do stuff", priority="high"
            )
            assert result["id"] == 1
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_thrums(self):
        mock_resp = self._make_mock_resp([
            {"id": 1, "creator": "kamaji", "title": "Test", "goal": "",
             "status": "pending", "priority": "normal",
             "created_at": "2026-02-15T10:00:00Z",
             "started_at": None, "completed_at": None}
        ])

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.get_thrums(status="pending")
            assert len(result) == 1
            assert result[0]["creator"] == "kamaji"

    @pytest.mark.asyncio
    async def test_get_thrum(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "creator": "kamaji", "title": "Test", "goal": "Do stuff",
            "plan": None, "status": "pending", "priority": "normal",
            "created_at": "2026-02-15T10:00:00Z",
            "started_at": None, "completed_at": None,
            "output": None, "tasks": [],
        })

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.get_thrum(1)
            assert result["id"] == 1
            assert result["tasks"] == []

    @pytest.mark.asyncio
    async def test_update_thrum(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "creator": "kamaji", "title": "Test", "goal": "Do stuff",
            "plan": "Step 1", "status": "active", "priority": "normal",
            "created_at": "2026-02-15T10:00:00Z",
            "started_at": "2026-02-15T10:01:00Z", "completed_at": None,
            "output": None, "tasks": [],
        })

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.patch.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await self.client.update_thrum(
                1, status="active", plan="Step 1"
            )
            assert result["status"] == "active"
            instance.patch.assert_called_once()
