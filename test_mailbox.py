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


# ---------------------------------------------------------------------------
# db.py — read tracking and feed
# ---------------------------------------------------------------------------


class TestDatabaseReadTracking:
    @pytest.mark.asyncio
    async def test_record_read(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        await mailbox_db.record_read(msg_id, "doot")
        msg = await mailbox_db.get_message_any(msg_id)
        assert len(msg["read_by"]) == 1
        assert msg["read_by"][0]["brother"] == "doot"

    @pytest.mark.asyncio
    async def test_record_read_idempotent(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        await mailbox_db.record_read(msg_id, "doot")
        await mailbox_db.record_read(msg_id, "doot")
        msg = await mailbox_db.get_message_any(msg_id)
        assert len(msg["read_by"]) == 1

    @pytest.mark.asyncio
    async def test_mark_read_inserts_into_message_reads(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        await mailbox_db.mark_read(msg_id, "oppy")
        msg = await mailbox_db.get_message_any(msg_id)
        brothers = [r["brother"] for r in msg["read_by"]]
        assert "oppy" in brothers

    @pytest.mark.asyncio
    async def test_get_message_includes_read_by(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        await mailbox_db.record_read(msg_id, "jerry")
        msg = await mailbox_db.get_message(msg_id, "oppy")
        assert msg is not None
        assert len(msg["read_by"]) == 1
        assert msg["read_by"][0]["brother"] == "jerry"

    @pytest.mark.asyncio
    async def test_multiple_readers(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        await mailbox_db.record_read(msg_id, "oppy")
        await mailbox_db.record_read(msg_id, "jerry")
        await mailbox_db.record_read(msg_id, "doot")
        msg = await mailbox_db.get_message_any(msg_id)
        brothers = {r["brother"] for r in msg["read_by"]}
        assert brothers == {"oppy", "jerry", "doot"}


class TestDatabaseFeed:
    @pytest.mark.asyncio
    async def test_feed_returns_all_messages(self):
        await mailbox_db.insert_message(
            sender="doot", subject="A", body="First", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="jerry", subject="B", body="Second", recipients=["doot"]
        )
        feed = await mailbox_db.get_feed()
        assert len(feed) == 2

    @pytest.mark.asyncio
    async def test_feed_sender_filter(self):
        await mailbox_db.insert_message(
            sender="doot", subject="A", body="First", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="jerry", subject="B", body="Second", recipients=["oppy"]
        )
        feed = await mailbox_db.get_feed(sender="doot")
        assert len(feed) == 1
        assert feed[0]["sender"] == "doot"

    @pytest.mark.asyncio
    async def test_feed_recipient_filter(self):
        await mailbox_db.insert_message(
            sender="doot", subject="A", body="For oppy", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="doot", subject="B", body="For jerry", recipients=["jerry"]
        )
        feed = await mailbox_db.get_feed(recipient="oppy")
        assert len(feed) == 1
        assert "oppy" in feed[0]["recipients"]

    @pytest.mark.asyncio
    async def test_feed_keyword_search_body(self):
        await mailbox_db.insert_message(
            sender="doot", subject="Greeting", body="Hello world", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="doot", subject="Other", body="Goodbye", recipients=["oppy"]
        )
        feed = await mailbox_db.get_feed(query="Hello")
        assert len(feed) == 1
        assert feed[0]["body"] == "Hello world"

    @pytest.mark.asyncio
    async def test_feed_keyword_search_subject(self):
        await mailbox_db.insert_message(
            sender="doot", subject="Architecture review", body="Body", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="doot", subject="Other", body="Body", recipients=["oppy"]
        )
        feed = await mailbox_db.get_feed(query="Architecture")
        assert len(feed) == 1
        assert feed[0]["subject"] == "Architecture review"

    @pytest.mark.asyncio
    async def test_feed_combined_filters(self):
        await mailbox_db.insert_message(
            sender="doot", subject="A", body="Hello", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="jerry", subject="B", body="Hello", recipients=["oppy"]
        )
        await mailbox_db.insert_message(
            sender="doot", subject="C", body="Goodbye", recipients=["oppy"]
        )
        feed = await mailbox_db.get_feed(sender="doot", query="Hello")
        assert len(feed) == 1
        assert feed[0]["subject"] == "A"

    @pytest.mark.asyncio
    async def test_feed_pagination(self):
        for i in range(5):
            await mailbox_db.insert_message(
                sender="doot", subject=f"Msg {i}", body=f"Body {i}", recipients=["oppy"]
            )
        feed = await mailbox_db.get_feed(limit=2, offset=0)
        assert len(feed) == 2
        feed2 = await mailbox_db.get_feed(limit=2, offset=2)
        assert len(feed2) == 2
        # No overlap
        ids1 = {m["id"] for m in feed}
        ids2 = {m["id"] for m in feed2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_feed_includes_recipients(self):
        await mailbox_db.insert_message(
            sender="doot", subject="Group", body="Body", recipients=["oppy", "jerry"]
        )
        feed = await mailbox_db.get_feed()
        assert len(feed) == 1
        assert set(feed[0]["recipients"]) == {"oppy", "jerry"}

    @pytest.mark.asyncio
    async def test_feed_includes_read_by(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        await mailbox_db.record_read(msg_id, "oppy")
        feed = await mailbox_db.get_feed()
        assert len(feed[0]["read_by"]) == 1
        assert feed[0]["read_by"][0]["brother"] == "oppy"

    @pytest.mark.asyncio
    async def test_feed_empty(self):
        feed = await mailbox_db.get_feed()
        assert feed == []


class TestDatabaseGetMessageAny:
    @pytest.mark.asyncio
    async def test_get_message_any(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Test", body="Body", recipients=["oppy"]
        )
        msg = await mailbox_db.get_message_any(msg_id)
        assert msg is not None
        assert msg["sender"] == "doot"
        assert "oppy" in msg["recipients"]

    @pytest.mark.asyncio
    async def test_get_message_any_non_recipient_can_view(self):
        """Any brother can view any message via get_message_any."""
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Private", body="For oppy only", recipients=["oppy"]
        )
        # Jerry is not a recipient, but get_message_any doesn't filter
        msg = await mailbox_db.get_message_any(msg_id)
        assert msg is not None
        assert msg["body"] == "For oppy only"

    @pytest.mark.asyncio
    async def test_get_message_any_not_found(self):
        msg = await mailbox_db.get_message_any(999)
        assert msg is None


# ---------------------------------------------------------------------------
# FastAPI — feed and view endpoints
# ---------------------------------------------------------------------------


class TestAPIFeed:
    @pytest.mark.asyncio
    async def test_feed_requires_auth(self, client):
        resp = await client.get("/api/v1/messages/feed")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_feed_returns_all_messages(self, client):
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Hello Oppy"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["jerry"], "body": "Hello Jerry"},
            headers=DOOT_HEADERS,
        )
        # Oppy can see messages sent to Jerry
        resp = await client.get("/api/v1/messages/feed", headers=OPPY_HEADERS)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_feed_sender_filter(self, client):
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "From doot"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["doot"], "body": "From oppy"},
            headers=OPPY_HEADERS,
        )
        resp = await client.get(
            "/api/v1/messages/feed", params={"sender": "doot"}, headers=JERRY_HEADERS
        )
        messages = resp.json()
        assert len(messages) == 1
        assert messages[0]["sender"] == "doot"

    @pytest.mark.asyncio
    async def test_feed_recipient_filter(self, client):
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "For oppy"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["jerry"], "body": "For jerry"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get(
            "/api/v1/messages/feed", params={"recipient": "oppy"}, headers=JERRY_HEADERS
        )
        messages = resp.json()
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_feed_keyword_search(self, client):
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Architecture review", "subject": "Design"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Training complete"},
            headers=JERRY_HEADERS,
        )
        resp = await client.get(
            "/api/v1/messages/feed", params={"q": "Architecture"}, headers=OPPY_HEADERS
        )
        messages = resp.json()
        assert len(messages) == 1
        assert "Architecture" in messages[0]["body"]

    @pytest.mark.asyncio
    async def test_feed_pagination(self, client):
        for i in range(5):
            await client.post(
                "/api/v1/messages",
                json={"recipients": ["oppy"], "body": f"Msg {i}"},
                headers=DOOT_HEADERS,
            )
        resp = await client.get(
            "/api/v1/messages/feed", params={"limit": 2, "offset": 0}, headers=OPPY_HEADERS
        )
        assert len(resp.json()) == 2
        resp2 = await client.get(
            "/api/v1/messages/feed", params={"limit": 2, "offset": 2}, headers=OPPY_HEADERS
        )
        assert len(resp2.json()) == 2

    @pytest.mark.asyncio
    async def test_feed_includes_read_by(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Read tracking test"},
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]
        # Oppy reads the message
        await client.post(f"/api/v1/messages/{msg_id}/read", headers=OPPY_HEADERS)
        # Feed should show read_by
        resp = await client.get("/api/v1/messages/feed", headers=JERRY_HEADERS)
        messages = resp.json()
        assert len(messages) == 1
        brothers = [r["brother"] for r in messages[0]["read_by"]]
        assert "oppy" in brothers


class TestAPIView:
    @pytest.mark.asyncio
    async def test_view_records_read(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "View test"},
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]
        resp = await client.post(f"/api/v1/messages/{msg_id}/view", headers=JERRY_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        brothers = [r["brother"] for r in data["read_by"]]
        assert "jerry" in brothers

    @pytest.mark.asyncio
    async def test_view_returns_detail(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy", "jerry"], "body": "Detail test", "subject": "Subj"},
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]
        resp = await client.post(f"/api/v1/messages/{msg_id}/view", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["sender"] == "doot"
        assert data["subject"] == "Subj"
        assert set(data["recipients"]) == {"oppy", "jerry"}

    @pytest.mark.asyncio
    async def test_view_not_found(self, client):
        resp = await client.post("/api/v1/messages/999/view", headers=DOOT_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_view_non_recipient_can_view(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "For oppy only"},
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]
        # Jerry is not a recipient
        resp = await client.post(f"/api/v1/messages/{msg_id}/view", headers=JERRY_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["body"] == "For oppy only"

    @pytest.mark.asyncio
    async def test_view_idempotent(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy"], "body": "Idempotent test"},
            headers=DOOT_HEADERS,
        )
        msg_id = resp.json()["id"]
        await client.post(f"/api/v1/messages/{msg_id}/view", headers=JERRY_HEADERS)
        resp = await client.post(f"/api/v1/messages/{msg_id}/view", headers=JERRY_HEADERS)
        assert resp.status_code == 200
        # Should still have exactly one read_by entry for jerry
        jerry_reads = [r for r in resp.json()["read_by"] if r["brother"] == "jerry"]
        assert len(jerry_reads) == 1


# ---------------------------------------------------------------------------
# MailboxClient — new methods
# ---------------------------------------------------------------------------


class TestMailboxClientFeedAndView:
    def setup_method(self):
        self.client = MailboxClient("http://localhost:8000", "test-key")

    def _make_mock_resp(self, json_data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def _make_async_client(self, get_resp=None, post_resp=None):
        instance = AsyncMock()
        if get_resp is not None:
            instance.get.return_value = get_resp
        if post_resp is not None:
            instance.post.return_value = post_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        return instance

    @pytest.mark.asyncio
    async def test_browse_feed(self):
        mock_resp = self._make_mock_resp([
            {"id": 1, "sender": "doot", "subject": "Hi", "body": "Hello",
             "created_at": "2026-02-07T00:00:00Z", "recipients": ["oppy"],
             "read_by": []}
        ])
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.browse_feed()
            assert len(result) == 1
            assert result[0]["sender"] == "doot"

    @pytest.mark.asyncio
    async def test_browse_feed_with_params(self):
        mock_resp = self._make_mock_resp([])
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance
            await self.client.browse_feed(sender="doot", recipient="oppy", query="hello", limit=10, offset=5)
            call_kwargs = instance.get.call_args
            params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
            assert params["sender"] == "doot"
            assert params["recipient"] == "oppy"
            assert params["q"] == "hello"
            assert params["limit"] == 10
            assert params["offset"] == 5

    @pytest.mark.asyncio
    async def test_view_message(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "sender": "doot", "subject": "Test", "body": "Body",
            "created_at": "2026-02-07T00:00:00Z", "recipients": ["oppy"],
            "read_by": [{"brother": "jerry", "read_at": "2026-02-07T00:00:00Z"}]
        })
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.view_message(1)
            assert result["id"] == 1
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_message_fallback_to_view(self):
        """When GET /messages/{id} returns 404, client falls back to POST /messages/{id}/view."""
        mock_404_resp = MagicMock()
        mock_404_resp.status_code = 404

        mock_view_resp = self._make_mock_resp({
            "id": 1, "sender": "doot", "subject": "Test", "body": "Body",
            "created_at": "2026-02-07T00:00:00Z", "recipients": ["oppy"],
            "read_by": []
        })

        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_404_resp
            instance.post.return_value = mock_view_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await self.client.read_message(1)
            assert result["id"] == 1
            # Should have called post on /view
            assert instance.post.called


# ---------------------------------------------------------------------------
# MCP tools — browse_feed and updated read_message
# ---------------------------------------------------------------------------


class TestMCPBrowseFeed:
    @pytest.mark.asyncio
    async def test_browse_feed_not_configured(self):
        import server
        original = server._mailbox
        server._mailbox = None
        try:
            result = await server.browse_feed()
            assert "not configured" in result.lower()
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_browse_feed_empty(self):
        import server
        mock_client = AsyncMock()
        mock_client.browse_feed.return_value = []
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.browse_feed()
            assert "No messages" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_browse_feed_with_messages(self):
        import server
        mock_client = AsyncMock()
        mock_client.browse_feed.return_value = [
            {
                "id": 1, "sender": "doot", "subject": "Hello",
                "body": "Test message", "created_at": "2026-02-07T00:00:00Z",
                "recipients": ["oppy", "jerry"],
                "read_by": [{"brother": "oppy", "read_at": "2026-02-07T01:00:00Z"}],
            }
        ]
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.browse_feed()
            assert "#1" in result
            assert "doot" in result
            assert "oppy, jerry" in result
            assert "Hello" in result
            assert "Read by: oppy" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_browse_feed_no_read_by(self):
        import server
        mock_client = AsyncMock()
        mock_client.browse_feed.return_value = [
            {
                "id": 1, "sender": "doot", "subject": "Hello",
                "body": "Test", "created_at": "2026-02-07T00:00:00Z",
                "recipients": ["oppy"], "read_by": [],
            }
        ]
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.browse_feed()
            assert "Read by" not in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_browse_feed_error(self):
        import server
        mock_client = AsyncMock()
        mock_client.browse_feed.side_effect = Exception("Connection refused")
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.browse_feed()
            assert "Error" in result
        finally:
            server._mailbox = original


class TestMCPReadMessageWithReadBy:
    @pytest.mark.asyncio
    async def test_read_message_shows_read_by(self):
        import server
        mock_client = AsyncMock()
        mock_client.read_message.return_value = {
            "id": 1, "sender": "oppy", "subject": "Design Review",
            "body": "Please review.",
            "created_at": "2026-02-07T10:00:00Z",
            "recipients": ["doot", "jerry"], "is_read": False,
            "read_by": [
                {"brother": "doot", "read_at": "2026-02-07T11:00:00Z"},
                {"brother": "jerry", "read_at": "2026-02-07T12:00:00Z"},
            ],
        }
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.read_message(1)
            assert "Read by: doot, jerry" in result
        finally:
            server._mailbox = original

    @pytest.mark.asyncio
    async def test_read_message_no_read_by(self):
        import server
        mock_client = AsyncMock()
        mock_client.read_message.return_value = {
            "id": 1, "sender": "oppy", "subject": "Test",
            "body": "Body",
            "created_at": "2026-02-07T10:00:00Z",
            "recipients": ["doot"], "is_read": False,
            "read_by": [],
        }
        original = server._mailbox
        server._mailbox = mock_client
        try:
            result = await server.read_message(1)
            assert "Read by" not in result
        finally:
            server._mailbox = original


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


# ---------------------------------------------------------------------------
# Timestamp formatting
# ---------------------------------------------------------------------------

from datetime import datetime, timezone
from timestamp_utils import format_timestamp


class TestFormatTimestamp:
    """Tests for the human-friendly timestamp formatter."""

    def _now(self, iso: str) -> datetime:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))

    def test_just_now(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:30:30Z")
        )
        assert "just now" in result
        assert "EST" in result

    def test_minutes_ago(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:45:00Z")
        )
        assert "15 min ago" in result

    def test_hours_ago(self):
        result = format_timestamp(
            "2026-02-08T15:00:00Z", now=self._now("2026-02-08T18:00:00Z")
        )
        assert "3 hr ago" in result

    def test_days_ago(self):
        result = format_timestamp(
            "2026-02-06T12:00:00Z", now=self._now("2026-02-08T12:00:00Z")
        )
        assert "2 days ago" in result

    def test_one_day_ago(self):
        result = format_timestamp(
            "2026-02-07T12:00:00Z", now=self._now("2026-02-08T12:00:00Z")
        )
        assert "1 day ago" in result

    def test_old_message_no_relative(self):
        """Messages older than 7 days don't show relative time."""
        result = format_timestamp(
            "2026-01-20T12:00:00Z", now=self._now("2026-02-08T12:00:00Z")
        )
        assert "ago" not in result
        assert "EST" in result

    def test_utc_to_est_conversion(self):
        # 15:30 UTC = 10:30 AM EST
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:30:00Z")
        )
        assert "10:30 AM" in result
        assert "EST" in result

    def test_custom_timezone(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z",
            tz_name="US/Pacific",
            now=self._now("2026-02-08T15:30:00Z"),
        )
        assert "7:30 AM" in result
        assert "PST" in result

    def test_future_timestamp(self):
        result = format_timestamp(
            "2026-02-08T16:00:00Z", now=self._now("2026-02-08T15:00:00Z")
        )
        assert "in the future" in result

    def test_format_includes_date(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:30:00Z")
        )
        assert "Feb 8" in result


# ---------------------------------------------------------------------------
# Tasks — database layer
# ---------------------------------------------------------------------------


class TestDatabaseTasks:
    @pytest.mark.asyncio
    async def test_insert_and_get_task(self):
        task_id = await mailbox_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="Review the code",
            subject="Code review",
            session_name="task-oppy-review-123",
            host="masuda",
            working_dir="~/projects/test",
        )
        assert task_id > 0

        task = await mailbox_db.get_task(task_id)
        assert task is not None
        assert task["creator"] == "doot"
        assert task["assignee"] == "oppy"
        assert task["prompt"] == "Review the code"
        assert task["subject"] == "Code review"
        assert task["status"] == "pending"
        assert task["session_name"] == "task-oppy-review-123"
        assert task["host"] == "masuda"
        assert task["working_dir"] == "~/projects/test"
        assert task["messages"] == []

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        task = await mailbox_db.get_task(999)
        assert task is None

    @pytest.mark.asyncio
    async def test_get_tasks_all(self):
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Task 2"
        )
        tasks = await mailbox_db.get_tasks()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_get_tasks_filter_assignee(self):
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Task 2"
        )
        tasks = await mailbox_db.get_tasks(assignee="oppy")
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_get_tasks_filter_status(self):
        t1 = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="doot", assignee="jerry", prompt="Task 2"
        )
        await mailbox_db.update_task(t1, status="completed")
        tasks = await mailbox_db.get_tasks(status="pending")
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "jerry"

    @pytest.mark.asyncio
    async def test_get_tasks_filter_creator(self):
        await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Task 1"
        )
        await mailbox_db.insert_task(
            creator="ian", assignee="oppy", prompt="Task 2"
        )
        tasks = await mailbox_db.get_tasks(creator="ian")
        assert len(tasks) == 1
        assert tasks[0]["creator"] == "ian"

    @pytest.mark.asyncio
    async def test_get_tasks_limit(self):
        for i in range(5):
            await mailbox_db.insert_task(
                creator="doot", assignee="oppy", prompt=f"Task {i}"
            )
        tasks = await mailbox_db.get_tasks(limit=3)
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_update_task_status(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Test"
        )
        updated = await mailbox_db.update_task(task_id, status="in_progress")
        assert updated is not None
        assert updated["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_task_output(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Test"
        )
        updated = await mailbox_db.update_task(
            task_id, status="completed", output="All done"
        )
        assert updated["status"] == "completed"
        assert updated["output"] == "All done"

    @pytest.mark.asyncio
    async def test_update_task_not_found(self):
        result = await mailbox_db.update_task(999, status="completed")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task_timestamps(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Test"
        )
        updated = await mailbox_db.update_task(
            task_id,
            status="completed",
            started_at="2026-02-09T10:00:00Z",
            completed_at="2026-02-09T10:30:00Z",
        )
        assert updated["started_at"] == "2026-02-09T10:00:00Z"
        assert updated["completed_at"] == "2026-02-09T10:30:00Z"


class TestDatabaseTaskLinkedMessages:
    @pytest.mark.asyncio
    async def test_message_with_task_id(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        msg_id = await mailbox_db.insert_message(
            sender="oppy",
            subject="Task received",
            body="I got it",
            recipients=["doot"],
            task_id=task_id,
        )
        task = await mailbox_db.get_task(task_id)
        assert len(task["messages"]) == 1
        assert task["messages"][0]["id"] == msg_id
        assert task["messages"][0]["body"] == "I got it"

    @pytest.mark.asyncio
    async def test_multiple_linked_messages(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        await mailbox_db.insert_message(
            sender="oppy", subject="Started", body="Working on it",
            recipients=["doot"], task_id=task_id,
        )
        await mailbox_db.insert_message(
            sender="oppy", subject="Done", body="All finished",
            recipients=["doot"], task_id=task_id,
        )
        task = await mailbox_db.get_task(task_id)
        assert len(task["messages"]) == 2

    @pytest.mark.asyncio
    async def test_message_without_task_id(self):
        msg_id = await mailbox_db.insert_message(
            sender="doot", subject="Hi", body="Hello", recipients=["oppy"]
        )
        assert msg_id > 0
        # Regular message still works without task_id

    @pytest.mark.asyncio
    async def test_linked_messages_include_recipients(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        await mailbox_db.insert_message(
            sender="oppy", subject="Status", body="Update",
            recipients=["doot", "jerry"], task_id=task_id,
        )
        task = await mailbox_db.get_task(task_id)
        assert set(task["messages"][0]["recipients"]) == {"doot", "jerry"}


# ---------------------------------------------------------------------------
# Tasks — API endpoints
# ---------------------------------------------------------------------------


class TestAPITasks:
    @pytest.mark.asyncio
    async def test_create_task(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Review the code",
                "subject": "Code review",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["message"] == "Task created"

    @pytest.mark.asyncio
    async def test_create_task_no_auth(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_tasks(self, client):
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Task 1", "subject": "First"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "Task 2", "subject": "Second"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get("/api/v1/tasks", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_filter_assignee(self, client):
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Task 1"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "Task 2"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get(
            "/api/v1/tasks", params={"assignee": "oppy"}, headers=DOOT_HEADERS
        )
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_list_tasks_filter_status(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Task 1"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]
        await client.post(
            "/api/v1/tasks",
            json={"assignee": "jerry", "prompt": "Task 2"},
            headers=DOOT_HEADERS,
        )
        # Mark first task completed
        await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get(
            "/api/v1/tasks", params={"status": "pending"}, headers=DOOT_HEADERS
        )
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["assignee"] == "jerry"

    @pytest.mark.asyncio
    async def test_get_task_detail(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "Do the thing",
                "subject": "Test task",
                "session_name": "task-oppy-test-123",
                "host": "masuda",
                "working_dir": "~/projects/test",
            },
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["creator"] == "doot"
        assert data["assignee"] == "oppy"
        assert data["prompt"] == "Do the thing"
        assert data["session_name"] == "task-oppy-test-123"
        assert data["messages"] == []

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, client):
        resp = await client.get("/api/v1/tasks/999", headers=DOOT_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_task_status(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=OPPY_HEADERS,  # assignee can update
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"
        assert resp.json()["started_at"] is not None

    @pytest.mark.asyncio
    async def test_update_task_completed_sets_timestamp(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed", "output": "All done"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        assert data["output"] == "All done"

    @pytest.mark.asyncio
    async def test_update_task_forbidden(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Jerry can't update a task assigned to oppy (and created by doot)
        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=JERRY_HEADERS,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_task_creator_can_update(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "cancelled"},
            headers=DOOT_HEADERS,  # creator can update
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_task_with_linked_messages(self, client):
        # Create task
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Send message linked to task
        await client.post(
            "/api/v1/messages",
            json={
                "recipients": ["doot"],
                "body": "Task received",
                "subject": "Ack",
                "task_id": task_id,
            },
            headers=OPPY_HEADERS,
        )

        # Get task detail - should include linked message
        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        data = resp.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["body"] == "Task received"


# ---------------------------------------------------------------------------
# MailboxClient — task methods
# ---------------------------------------------------------------------------


class TestMailboxClientTasks:
    def setup_method(self):
        self.client = MailboxClient("http://localhost:8000", "test-key")

    def _make_mock_resp(self, json_data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def _make_async_client(self, get_resp=None, post_resp=None, patch_resp=None):
        instance = AsyncMock()
        if get_resp is not None:
            instance.get.return_value = get_resp
        if post_resp is not None:
            instance.post.return_value = post_resp
        if patch_resp is not None:
            instance.patch.return_value = patch_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        return instance

    @pytest.mark.asyncio
    async def test_create_task(self):
        mock_resp = self._make_mock_resp({"id": 1, "message": "Task created"})
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.create_task("oppy", "Do stuff", subject="Test")
            assert result["id"] == 1
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tasks(self):
        mock_resp = self._make_mock_resp([
            {"id": 1, "creator": "doot", "assignee": "oppy", "subject": "Test",
             "status": "pending", "created_at": "2026-02-09T10:00:00Z",
             "started_at": None, "completed_at": None}
        ])
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.get_tasks(assignee="oppy")
            assert len(result) == 1
            assert result[0]["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_get_task(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "creator": "doot", "assignee": "oppy", "subject": "Test",
            "prompt": "Do stuff", "status": "pending",
            "created_at": "2026-02-09T10:00:00Z",
            "started_at": None, "completed_at": None,
            "session_name": None, "host": None, "working_dir": None,
            "output": None, "messages": [],
        })
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.get_task(1)
            assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_update_task(self):
        mock_resp = self._make_mock_resp({
            "id": 1, "creator": "doot", "assignee": "oppy", "subject": "Test",
            "prompt": "Do stuff", "status": "completed",
            "created_at": "2026-02-09T10:00:00Z",
            "started_at": "2026-02-09T10:01:00Z",
            "completed_at": "2026-02-09T10:30:00Z",
            "session_name": None, "host": None, "working_dir": None,
            "output": "All done", "messages": [],
        })
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(patch_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.update_task(1, status="completed", output="All done")
            assert result["status"] == "completed"
            instance.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_with_task_id(self):
        mock_resp = self._make_mock_resp({"id": 5, "message": "Message sent"})
        with patch("mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(post_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.send_message(
                ["doot"], "Task done", subject="Done", task_id=3
            )
            assert result["id"] == 5
            # Verify task_id was included in payload
            call_kwargs = instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["task_id"] == 3


# ---------------------------------------------------------------------------
# Task Events — database layer
# ---------------------------------------------------------------------------


class TestDatabaseTaskEvents:
    @pytest.mark.asyncio
    async def test_insert_and_get_events(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        ev1 = await mailbox_db.insert_task_event(
            task_id, event_type="PostToolUse", summary="ran: npm test", tool_name="Bash"
        )
        ev2 = await mailbox_db.insert_task_event(
            task_id, event_type="PostToolUse", summary="edited: src/main.py", tool_name="Edit"
        )
        assert ev1 > 0
        assert ev2 > ev1

        events = await mailbox_db.get_task_events(task_id)
        assert len(events) == 2
        assert events[0]["event_type"] == "PostToolUse"
        assert events[0]["tool_name"] == "Bash"
        assert events[0]["summary"] == "ran: npm test"
        assert events[1]["tool_name"] == "Edit"

    @pytest.mark.asyncio
    async def test_events_empty_for_new_task(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        events = await mailbox_db.get_task_events(task_id)
        assert events == []

    @pytest.mark.asyncio
    async def test_events_included_in_get_task(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        await mailbox_db.insert_task_event(
            task_id, event_type="PostToolUse", summary="ran: ls", tool_name="Bash"
        )
        await mailbox_db.insert_task_event(
            task_id, event_type="Stop", summary="Session ended"
        )
        task = await mailbox_db.get_task(task_id)
        assert "events" in task
        assert len(task["events"]) == 2
        assert task["events"][0]["summary"] == "ran: ls"
        assert task["events"][1]["event_type"] == "Stop"
        assert task["events"][1]["tool_name"] is None

    @pytest.mark.asyncio
    async def test_event_null_tool_name(self):
        task_id = await mailbox_db.insert_task(
            creator="doot", assignee="oppy", prompt="Do stuff"
        )
        ev_id = await mailbox_db.insert_task_event(
            task_id, event_type="Stop", summary="Session ended", tool_name=None
        )
        events = await mailbox_db.get_task_events(task_id)
        assert len(events) == 1
        assert events[0]["tool_name"] is None


# ---------------------------------------------------------------------------
# Task Events — API endpoints
# ---------------------------------------------------------------------------


class TestAPITaskEvents:
    @pytest.mark.asyncio
    async def test_log_event(self, client):
        # Create a task first
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Log an event
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={
                "event_type": "PostToolUse",
                "tool_name": "Bash",
                "summary": "ran: pytest tests/",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_type"] == "PostToolUse"
        assert data["tool_name"] == "Bash"
        assert data["summary"] == "ran: pytest tests/"
        assert data["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_log_event_no_tool_name(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "Stop", "summary": "Session ended"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_name"] is None

    @pytest.mark.asyncio
    async def test_log_event_task_not_found(self, client):
        resp = await client.post(
            "/api/v1/tasks/9999/log",
            json={"event_type": "Stop", "summary": "Session ended"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_log_event_no_auth(self, client):
        resp = await client.post(
            "/api/v1/tasks/1/log",
            json={"event_type": "Stop", "summary": "Session ended"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_events_in_task_detail(self, client):
        # Create task
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff", "subject": "Test"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Log events
        await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "PostToolUse", "tool_name": "Bash", "summary": "ran: ls"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "PostToolUse", "tool_name": "Edit", "summary": "edited: main.py"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "Stop", "summary": "Session ended"},
            headers=DOOT_HEADERS,
        )

        # Get task detail — should include events
        resp = await client.get(f"/api/v1/tasks/{task_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        task = resp.json()
        assert len(task["events"]) == 3
        assert task["events"][0]["tool_name"] == "Bash"
        assert task["events"][2]["event_type"] == "Stop"

    @pytest.mark.asyncio
    async def test_log_event_validation(self, client):
        resp = await client.post(
            "/api/v1/tasks",
            json={"assignee": "oppy", "prompt": "Do stuff"},
            headers=DOOT_HEADERS,
        )
        task_id = resp.json()["id"]

        # Missing required fields
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/log",
            json={"event_type": "PostToolUse"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422
