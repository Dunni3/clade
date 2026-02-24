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
    async def test_create_task_with_parent_task_id(self):
        mock_resp = self._make_mock_resp({"id": 10})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.create_task(
                assignee="oppy", prompt="Do work", subject="Test", parent_task_id=5
            )
            assert result["id"] == 10
            instance.post.assert_called_once()
            call_kwargs = instance.post.call_args
            payload = call_kwargs.kwargs["json"]
            assert payload["parent_task_id"] == 5

    @pytest.mark.asyncio
    async def test_create_task_without_parent_task_id(self):
        mock_resp = self._make_mock_resp({"id": 11})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.create_task(
                assignee="oppy", prompt="Do work", subject="Test"
            )
            assert result["id"] == 11
            instance.post.assert_called_once()
            call_kwargs = instance.post.call_args
            payload = call_kwargs.kwargs["json"]
            assert "parent_task_id" not in payload

    @pytest.mark.asyncio
    async def test_create_morsel(self):
        mock_resp = self._make_mock_resp({"id": 1, "body": "A note"})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.create_morsel(
                body="A note",
                tags=["debug", "test"],
                links=[{"object_type": "task", "object_id": "42"}],
            )
            assert result["id"] == 1
            instance.post.assert_called_once()
            call_kwargs = instance.post.call_args
            payload = call_kwargs.kwargs["json"]
            assert payload["body"] == "A note"
            assert payload["tags"] == ["debug", "test"]
            assert payload["links"] == [{"object_type": "task", "object_id": "42"}]

    @pytest.mark.asyncio
    async def test_get_morsels(self):
        mock_resp = self._make_mock_resp([
            {"id": 1, "creator": "doot", "body": "Note 1", "tags": [], "created_at": "2026-02-20T10:00:00Z"},
        ])

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.get_morsels(creator="doot", tag="debug", limit=10)
            assert len(result) == 1
            assert result[0]["creator"] == "doot"
            instance.get.assert_called_once()
            call_kwargs = instance.get.call_args
            params = call_kwargs.kwargs["params"]
            assert params["creator"] == "doot"
            assert params["tag"] == "debug"
            assert params["limit"] == 10

    @pytest.mark.asyncio
    async def test_get_morsel(self):
        mock_resp = self._make_mock_resp({
            "id": 5, "creator": "oppy", "body": "Detailed note", "tags": ["info"],
            "created_at": "2026-02-20T10:00:00Z",
        })

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.get_morsel(5)
            assert result["id"] == 5
            assert result["body"] == "Detailed note"
            instance.get.assert_called_once()
            call_url = instance.get.call_args.args[0]
            assert "/morsels/5" in call_url

    @pytest.mark.asyncio
    async def test_get_trees(self):
        mock_resp = self._make_mock_resp([
            {"root": {"id": 1, "subject": "Root task", "assignee": "kamaji"},
             "total_tasks": 3, "status_counts": {"completed": 2, "in_progress": 1}},
        ])

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.get_trees(limit=10)
            assert len(result) == 1
            assert result[0]["total_tasks"] == 3
            instance.get.assert_called_once()
            call_url = instance.get.call_args.args[0]
            assert "/trees" in call_url

    @pytest.mark.asyncio
    async def test_get_tree(self):
        mock_resp = self._make_mock_resp({
            "root": {
                "id": 1, "subject": "Root", "assignee": "kamaji", "status": "completed",
                "children": [
                    {"id": 2, "subject": "Child", "assignee": "oppy", "status": "completed", "children": []},
                ],
            }
        })

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.get_tree(1)
            assert result["root"]["id"] == 1
            assert len(result["root"]["children"]) == 1
            instance.get.assert_called_once()
            call_url = instance.get.call_args.args[0]
            assert "/trees/1" in call_url

    @pytest.mark.asyncio
    async def test_create_task_with_on_complete(self):
        mock_resp = self._make_mock_resp({"id": 12})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.create_task(
                assignee="oppy",
                prompt="Do work",
                subject="Test",
                on_complete="Deploy after completion",
            )
            assert result["id"] == 12
            instance.post.assert_called_once()
            call_kwargs = instance.post.call_args
            payload = call_kwargs.kwargs["json"]
            assert payload["on_complete"] == "Deploy after completion"

    @pytest.mark.asyncio
    async def test_create_task_without_on_complete(self):
        mock_resp = self._make_mock_resp({"id": 13})

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance

            result = await self.client.create_task(
                assignee="oppy", prompt="Do work", subject="Test"
            )
            assert result["id"] == 13
            instance.post.assert_called_once()
            call_kwargs = instance.post.call_args
            payload = call_kwargs.kwargs["json"]
            assert "on_complete" not in payload

    def test_register_ember_sync_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("clade.communication.mailbox_client.httpx.put", return_value=mock_resp) as mock_put:
            result = self.client.register_ember_sync("oppy", "http://100.1.2.3:8100")
            assert result is True
            mock_put.assert_called_once()
            call_kwargs = mock_put.call_args
            assert call_kwargs.kwargs["json"] == {"ember_url": "http://100.1.2.3:8100"}
            assert "/embers/oppy" in call_kwargs.args[0]

    def test_register_ember_sync_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch("clade.communication.mailbox_client.httpx.put", return_value=mock_resp):
            result = self.client.register_ember_sync("oppy", "http://100.1.2.3:8100")
            assert result is False
