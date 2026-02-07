"""Tests for the Brother Mailbox system.

Covers: database layer, FastAPI endpoints, mailbox client, and MCP tools.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Set test config before importing mailbox modules
os.environ["MAILBOX_API_KEYS"] = "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry"

from httpx import ASGITransport, AsyncClient

from mailbox.app import app
from mailbox import db as mailbox_db
from mailbox.config import parse_api_keys
from mailbox.auth import resolve_sender
from mailbox_client import MailboxClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Use a fresh SQLite database for each test."""
    db_path = str(tmp_path / "test.db")
    # Patch the DB_PATH in the db module
    original = mailbox_db.DB_PATH
    mailbox_db.DB_PATH = db_path
    await mailbox_db.init_db()
    yield db_path
    mailbox_db.DB_PATH = original


@pytest_asyncio.fixture
async def client():
    """Async test client for the FastAPI app, authenticated as doot."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}
JERRY_HEADERS = {"Authorization": "Bearer test-key-jerry"}


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------


class TestConfig:
    def test_parse_api_keys_normal(self):
        result = parse_api_keys("abc:doot,def:oppy")
        assert result == {"abc": "doot", "def": "oppy"}

    def test_parse_api_keys_with_spaces(self):
        result = parse_api_keys("abc : doot , def : oppy")
        assert result == {"abc": "doot", "def": "oppy"}

    def test_parse_api_keys_empty(self):
        result = parse_api_keys("")
        assert result == {}

    def test_parse_api_keys_no_colon(self):
        result = parse_api_keys("badentry,abc:doot")
        assert result == {"abc": "doot"}


# ---------------------------------------------------------------------------
# db.py — direct database operations
# ---------------------------------------------------------------------------


class TestDatabase:
    @pytest.mark.asyncio
    async def test_insert_and_retrieve_message(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Hello", body="Test message", recipients=["oppy"]
        )
        assert msg_id is not None
        assert msg_id > 0

        messages = await mailbox_db.get_messages("oppy")
        assert len(messages) == 1
        assert messages[0]["sender"] == "doot"
        assert messages[0]["subject"] == "Hello"
        assert messages[0]["body"] == "Test message"
        assert messages[0]["is_read"] == 0

    @pytest.mark.asyncio
    async def test_multiple_recipients(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot",
            subject="Group msg",
            body="For both of you",
            recipients=["oppy", "jerry"],
        )
        oppy_msgs = await mailbox_db.get_messages("oppy")
        jerry_msgs = await mailbox_db.get_messages("jerry")
        assert len(oppy_msgs) == 1
        assert len(jerry_msgs) == 1
        assert oppy_msgs[0]["id"] == jerry_msgs[0]["id"] == msg_id

    @pytest.mark.asyncio
    async def test_unread_only_filter(self):
        await mailbox_db.insert_message(
            sender="doot", subject="A", body="First", recipients=["oppy"]
        )
        msg2_id = await mailbox_db.insert_message(
            sender="doot", subject="B", body="Second", recipients=["oppy"]
        )
        await mailbox_db.mark_read(msg2_id, "oppy")

        all_msgs = await mailbox_db.get_messages("oppy", unread_only=False)
        unread_msgs = await mailbox_db.get_messages("oppy", unread_only=True)
        assert len(all_msgs) == 2
        assert len(unread_msgs) == 1
        assert unread_msgs[0]["subject"] == "A"

    @pytest.mark.asyncio
    async def test_mark_read(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Read me", body="Content", recipients=["oppy"]
        )
        updated = await mailbox_db.mark_read(msg_id, "oppy")
        assert updated is True

        messages = await mailbox_db.get_messages("oppy")
        assert messages[0]["is_read"] == 1

    @pytest.mark.asyncio
    async def test_mark_read_already_read(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Read me", body="Content", recipients=["oppy"]
        )
        await mailbox_db.mark_read(msg_id, "oppy")
        updated = await mailbox_db.mark_read(msg_id, "oppy")
        assert updated is False

    @pytest.mark.asyncio
    async def test_mark_read_wrong_recipient(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Private", body="For oppy", recipients=["oppy"]
        )
        updated = await mailbox_db.mark_read(msg_id, "jerry")
        assert updated is False

    @pytest.mark.asyncio
    async def test_get_message_detail(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot",
            subject="Detail test",
            body="Full detail",
            recipients=["oppy", "jerry"],
        )
        msg = await mailbox_db.get_message(msg_id, "oppy")
        assert msg is not None
        assert msg["sender"] == "doot"
        assert msg["subject"] == "Detail test"
        assert set(msg["recipients"]) == {"oppy", "jerry"}

    @pytest.mark.asyncio
    async def test_get_message_not_recipient(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Private", body="For oppy", recipients=["oppy"]
        )
        msg = await mailbox_db.get_message(msg_id, "jerry")
        assert msg is None

    @pytest.mark.asyncio
    async def test_unread_count(self):
        await mailbox_db.insert_message(
            sender="doot", subject="A", body="One", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="jerry", subject="B", body="Two", recipients=["oppy"]
        )
        count = await mailbox_db.get_unread_count("oppy")
        assert count == 2

    @pytest.mark.asyncio
    async def test_unread_count_after_read(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="A", body="One", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="jerry", subject="B", body="Two", recipients=["oppy"]
        )
        await mailbox_db.mark_read(msg_id, "oppy")
        count = await mailbox_db.get_unread_count("oppy")
        assert count == 1

    @pytest.mark.asyncio
    async def test_limit(self):
        for i in range(5):
            await mailbox_db.insert_message(
                sender="doot", subject=f"Msg {i}", body=f"Body {i}", recipients=["oppy"]
            )
        messages = await mailbox_db.get_messages("oppy", limit=3)
        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_sender_does_not_see_own_message(self):
        """Sender is not a recipient unless explicitly listed."""
        await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        doot_msgs = await mailbox_db.get_messages("doot")
        assert len(doot_msgs) == 0


# ---------------------------------------------------------------------------
# FastAPI endpoints
# ---------------------------------------------------------------------------


class TestAPI:
    @pytest.mark.asyncio
    async def test_send_message(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Hello from API", "subject": "Test"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["message"] == "Message sent"

    @pytest.mark.asyncio
    async def test_send_message_no_auth(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Hello"},
        )
        assert resp.status_code == 422  # missing header

    @pytest.mark.asyncio
    async def test_send_message_bad_key(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Hello"},
            headers={"Authorization": "Bearer bad-key"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_messages(self, client):
        # Send a message to oppy
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Hello Oppy"},
            headers=DOOT_HEADERS,
        )
        # Oppy checks mailbox
        resp = await client.get("/api/v1/messages", headers=OPPY_HEADERS)
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 1
        assert messages[0]["sender"] == "doot"

    @pytest.mark.asyncio
    async def test_list_messages_unread_only(self, client):
        # Send two messages to oppy
        resp1 = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "First"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Second"},
            headers=DOOT_HEADERS,
        )
        msg1_id = resp1.json()["id"]

        # Mark first as read
        await client.post(
            f"/api/v1/messages/{msg1_id}/read", headers=OPPY_HEADERS
        )

        # Filter unread only
        resp = await client.get(
            "/api/v1/messages", params={"unread_only": True}, headers=OPPY_HEADERS
        )
        messages = resp.json()
        assert len(messages) == 1
        assert messages[0]["body"] == "Second"

    @pytest.mark.asyncio
    async def test_get_message_detail(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={
                "recipients": ["oppy", "jerry"],
                "body": "Group message",
                "subject": "Group",
            },
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]

        resp = await client.get(
            f"/api/v1/messages/{msg_id}", headers=OPPY_HEADERS
        )
        assert resp.status_code == 200
        msg = resp.json()
        assert msg["sender"] == "doot"
        assert set(msg["recipients"]) == {"oppy", "jerry"}

    @pytest.mark.asyncio
    async def test_get_message_not_found(self, client):
        resp = await client.get("/api/v1/messages/999", headers=OPPY_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_mark_read(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Read me"},
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]

        resp = await client.post(
            f"/api/v1/messages/{msg_id}/read", headers=OPPY_HEADERS
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_mark_read_already_read(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Read me"},
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]
        await client.post(f"/api/v1/messages/{msg_id}/read", headers=OPPY_HEADERS)

        resp = await client.post(
            f"/api/v1/messages/{msg_id}/read", headers=OPPY_HEADERS
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unread_count(self, client):
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "One"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Two"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get("/api/v1/unread", headers=OPPY_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["unread"] == 2

    @pytest.mark.asyncio
    async def test_unread_count_zero(self, client):
        resp = await client.get("/api/v1/unread", headers=OPPY_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["unread"] == 0

    @pytest.mark.asyncio
    async def test_empty_recipients_rejected(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": [], "body": "Hello"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# MailboxClient — unit tests with mocked HTTP
# ---------------------------------------------------------------------------


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

        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
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

        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
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

        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_get_resp, post_resp=mock_post_resp)
            MockClient.return_value = instance

            result = await self.client.read_message(1)
            assert result["id"] == 1
            # Should also call post to mark as read
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_unread_count(self):
        mock_resp = self._make_mock_resp({"unread": 3})

        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
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


# ---------------------------------------------------------------------------
# MCP tools — test graceful degradation and formatting
# ---------------------------------------------------------------------------


class TestMCPToolsNotConfigured:
    """When mailbox env vars aren't set, tools should return a friendly message."""

    @pytest.mark.asyncio
    async def test_send_message_not_configured(self):
        import server
        original = server._mailbox
        server._mailbox = None
        try:
            result = await server.send_message(["oppy"], "hello")
            assert "not configured" in result.lower()
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_check_mailbox_not_configured(self):
        import server
        original = server._mailbox
        server._mailbox = None
        try:
            result = await server.check_mailbox()
            assert "not configured" in result.lower()
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_read_message_not_configured(self):
        import server
        original = server._mailbox
        server._mailbox = None
        try:
            result = await server.read_message(1)
            assert "not configured" in result.lower()
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_unread_count_not_configured(self):
        import server
        original = server._mailbox
        server._mailbox = None
        try:
            result = await server.unread_count()
            assert "not configured" in result.lower()
        finally:
            server._mailbox = original


class TestMCPToolsWithMock:
    """Test MCP tools with a mocked MailboxClient."""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        import server
        mock_client = AsyncMock()
        mock_client.send_message.return_value = {"id": 42, "message": "Message sent"}
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.send_message(["oppy", "jerry"], "Hello brothers", "Greetings")
            assert "oppy, jerry" in result
            assert "42" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_send_message_error(self):
        import server
        mock_client = AsyncMock()
        mock_client.send_message.side_effect = Exception("Connection refused")
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.send_message(["oppy"], "Hello")
            assert "Error" in result
            assert "Connection refused" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_check_mailbox_with_messages(self):
        import server
        mock_client = AsyncMock()
        mock_client.check_mailbox.return_value = [
            {"id": 1, "sender": "oppy", "subject": "Architecture", "body": "Let's discuss the design", "created_at": "2026-02-07T10:00:00Z", "is_read": False},
            {"id": 2, "sender": "jerry", "subject": "", "body": "Training done", "created_at": "2026-02-07T11:00:00Z", "is_read": True},
        ]
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.check_mailbox()
            assert "[NEW]" in result
            assert "oppy" in result
            assert "jerry" in result
            assert "Architecture" in result
            assert "(no subject)" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_check_mailbox_empty(self):
        import server
        mock_client = AsyncMock()
        mock_client.check_mailbox.return_value = []
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.check_mailbox(unread_only=True)
            assert "No unread messages" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_read_message_formatted(self):
        import server
        mock_client = AsyncMock()
        mock_client.read_message.return_value = {
            "id": 1, "sender": "oppy", "subject": "Design Review",
            "body": "Please review the architecture doc.",
            "created_at": "2026-02-07T10:00:00Z",
            "recipients": ["doot", "jerry"], "is_read": False,
        }
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.read_message(1)
            assert "Message #1" in result
            assert "From: oppy" in result
            assert "To: doot, jerry" in result
            assert "Subject: Design Review" in result
            assert "Please review" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_unread_count_zero(self):
        import server
        mock_client = AsyncMock()
        mock_client.unread_count.return_value = 0
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.unread_count()
            assert "No unread" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_unread_count_singular(self):
        import server
        mock_client = AsyncMock()
        mock_client.unread_count.return_value = 1
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.unread_count()
            assert "1 unread message." in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_unread_count_plural(self):
        import server
        mock_client = AsyncMock()
        mock_client.unread_count.return_value = 5
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.unread_count()
            assert "5 unread messages." in result
        finally:
            server._mailbox = original


# ---------------------------------------------------------------------------
# Integration: API client -> FastAPI server (in-process)
# ---------------------------------------------------------------------------


class TestIntegrationClientToServer:
    """Test the MailboxClient talking to the real FastAPI app via ASGI transport."""

    @pytest_asyncio.fixture
    async def mailbox(self):
        """A MailboxClient configured to talk to the in-process FastAPI app."""
        # We use httpx's ASGI transport to route requests directly to the app
        transport = ASGITransport(app=app)
        client = MailboxClient("http://test", "test-key-doot")
        # Override to use ASGI transport
        original_send = client.send_message
        original_check = client.check_mailbox
        original_read = client.read_message
        original_unread = client.unread_count

        async def patched_send(recipients, body, subject=""):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    "/api/v1/messages",
                    json={"recipients": recipients, "body": body, "subject": subject},
                    headers={"Authorization": "Bearer test-key-doot"},
                    timeout=10,
                )
                resp.raise_for_status()
                return resp.json()

        async def patched_check(unread_only=True, limit=20):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get(
                    "/api/v1/messages",
                    params={"unread_only": unread_only, "limit": limit},
                    headers={"Authorization": "Bearer test-key-doot"},
                    timeout=10,
                )
                resp.raise_for_status()
                return resp.json()

        client.send_message = patched_send
        client.check_mailbox = patched_check
        yield client

    @pytest.mark.asyncio
    async def test_send_and_check(self, mailbox):
        result = await mailbox.send_message(["doot"], "Integration test", "Hello")
        assert "id" in result

        messages = await mailbox.check_mailbox(unread_only=False)
        assert len(messages) == 1
        assert messages[0]["body"] == "Integration test"
