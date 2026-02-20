"""Tests for the Hearth communication system.

Covers: database layer, FastAPI endpoints, mailbox client, and MCP tools.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Set test config before importing mailbox modules
os.environ["MAILBOX_API_KEYS"] = "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian"

from httpx import ASGITransport, AsyncClient
from mcp.server.fastmcp import FastMCP

from hearth.app import app
from hearth import db as mailbox_db
from hearth.config import parse_api_keys
from hearth.auth import resolve_sender
from clade.communication.mailbox_client import MailboxClient
from clade.mcp.tools.mailbox_tools import create_mailbox_tools
from clade.mcp.tools.task_tools import create_task_tools
from clade.tasks.ssh_task import TaskResult


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

    @pytest.mark.asyncio
    async def test_send_to_unknown_recipient_rejected(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["nonexistent"], "body": "Hello"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422
        assert "nonexistent" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_send_to_mix_known_and_unknown_rejected(self, client):
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["oppy", "fakename"], "body": "Hello"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422
        assert "fakename" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_send_to_db_registered_recipient_accepted(self, client):
        """Recipients registered via the API (not just env vars) should be accepted."""
        await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "key-curie"},
            headers=DOOT_HEADERS,
        )
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["curie"], "body": "Hello curie"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200


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


# ---------------------------------------------------------------------------
# MCP tools — test graceful degradation and formatting
# ---------------------------------------------------------------------------


def _make_tools(mailbox):
    """Create mailbox tools with the given mailbox client (or None)."""
    mcp = FastMCP("test")
    return create_mailbox_tools(mcp, mailbox)


class TestMCPToolsNotConfigured:
    """When mailbox is None, tools should return a friendly message."""

    @pytest.mark.asyncio
    async def test_send_message_not_configured(self):
        tools = _make_tools(None)
        result = await tools["send_message"](["oppy"], "hello")
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_check_mailbox_not_configured(self):
        tools = _make_tools(None)
        result = await tools["check_mailbox"]()
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_read_message_not_configured(self):
        tools = _make_tools(None)
        result = await tools["read_message"](1)
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_unread_count_not_configured(self):
        tools = _make_tools(None)
        result = await tools["unread_count"]()
        assert "not configured" in result.lower()


class TestMCPToolsWithMock:
    """Test MCP tools with a mocked MailboxClient."""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        mock_client = AsyncMock()
        mock_client.send_message.return_value = {"id": 42, "message": "Message sent"}
        tools = _make_tools(mock_client)
        result = await tools["send_message"](["oppy", "jerry"], "Hello brothers", "Greetings")
        assert "oppy, jerry" in result
        assert "42" in result

    @pytest.mark.asyncio
    async def test_send_message_error(self):
        mock_client = AsyncMock()
        mock_client.send_message.side_effect = Exception("Connection refused")
        tools = _make_tools(mock_client)
        result = await tools["send_message"](["oppy"], "Hello")
        assert "Error" in result
        assert "Connection refused" in result

    @pytest.mark.asyncio
    async def test_check_mailbox_with_messages(self):
        mock_client = AsyncMock()
        mock_client.check_mailbox.return_value = [
            {"id": 1, "sender": "oppy", "subject": "Architecture", "body": "Let's discuss the design", "created_at": "2026-02-07T10:00:00Z", "is_read": False},
            {"id": 2, "sender": "jerry", "subject": "", "body": "Training done", "created_at": "2026-02-07T11:00:00Z", "is_read": True},
        ]
        tools = _make_tools(mock_client)
        result = await tools["check_mailbox"]()
        assert "[NEW]" in result
        assert "oppy" in result
        assert "jerry" in result
        assert "Architecture" in result
        assert "(no subject)" in result

    @pytest.mark.asyncio
    async def test_check_mailbox_empty(self):
        mock_client = AsyncMock()
        mock_client.check_mailbox.return_value = []
        tools = _make_tools(mock_client)
        result = await tools["check_mailbox"](unread_only=True)
        assert "No unread messages" in result

    @pytest.mark.asyncio
    async def test_read_message_formatted(self):
        mock_client = AsyncMock()
        mock_client.read_message.return_value = {
            "id": 1, "sender": "oppy", "subject": "Design Review",
            "body": "Please review the architecture doc.",
            "created_at": "2026-02-07T10:00:00Z",
            "recipients": ["doot", "jerry"], "is_read": False,
        }
        tools = _make_tools(mock_client)
        result = await tools["read_message"](1)
        assert "Message #1" in result
        assert "From: oppy" in result
        assert "To: doot, jerry" in result
        assert "Subject: Design Review" in result
        assert "Please review" in result

    @pytest.mark.asyncio
    async def test_unread_count_zero(self):
        mock_client = AsyncMock()
        mock_client.unread_count.return_value = 0
        tools = _make_tools(mock_client)
        result = await tools["unread_count"]()
        assert "No unread" in result

    @pytest.mark.asyncio
    async def test_unread_count_singular(self):
        mock_client = AsyncMock()
        mock_client.unread_count.return_value = 1
        tools = _make_tools(mock_client)
        result = await tools["unread_count"]()
        assert "1 unread message." in result

    @pytest.mark.asyncio
    async def test_unread_count_plural(self):
        mock_client = AsyncMock()
        mock_client.unread_count.return_value = 5
        tools = _make_tools(mock_client)
        result = await tools["unread_count"]()
        assert "5 unread messages." in result


# ---------------------------------------------------------------------------
# Integration: API client -> FastAPI server (in-process)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# db.py — read tracking and feed
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# db.py — API keys
# ---------------------------------------------------------------------------


class TestDatabaseGetAllMemberNames:
    @pytest.mark.asyncio
    async def test_empty_db(self):
        names = await mailbox_db.get_all_member_names()
        assert names == set()

    @pytest.mark.asyncio
    async def test_with_keys(self):
        await mailbox_db.insert_api_key("curie", "key-1")
        await mailbox_db.insert_api_key("darwin", "key-2")
        names = await mailbox_db.get_all_member_names()
        assert names == {"curie", "darwin"}


class TestDatabaseApiKeys:
    @pytest.mark.asyncio
    async def test_insert_and_lookup(self):
        ok = await mailbox_db.insert_api_key("curie", "secret-key-curie")
        assert ok is True
        name = await mailbox_db.get_api_key_by_key("secret-key-curie")
        assert name == "curie"

    @pytest.mark.asyncio
    async def test_lookup_not_found(self):
        name = await mailbox_db.get_api_key_by_key("nonexistent-key")
        assert name is None

    @pytest.mark.asyncio
    async def test_duplicate_name(self):
        await mailbox_db.insert_api_key("curie", "key-1")
        ok = await mailbox_db.insert_api_key("curie", "key-2")
        assert ok is False

    @pytest.mark.asyncio
    async def test_duplicate_key(self):
        await mailbox_db.insert_api_key("curie", "same-key")
        ok = await mailbox_db.insert_api_key("darwin", "same-key")
        assert ok is False

    @pytest.mark.asyncio
    async def test_list_keys(self):
        await mailbox_db.insert_api_key("curie", "key-1")
        await mailbox_db.insert_api_key("darwin", "key-2")
        keys = await mailbox_db.list_api_keys()
        assert len(keys) == 2
        names = [k["name"] for k in keys]
        assert "curie" in names
        assert "darwin" in names
        # Should NOT contain the actual key values
        for k in keys:
            assert "key" not in k or k.get("key") is None

    @pytest.mark.asyncio
    async def test_list_keys_empty(self):
        keys = await mailbox_db.list_api_keys()
        assert keys == []

    @pytest.mark.asyncio
    async def test_delete_key(self):
        await mailbox_db.insert_api_key("curie", "key-1")
        deleted = await mailbox_db.delete_api_key("curie")
        assert deleted is True
        name = await mailbox_db.get_api_key_by_key("key-1")
        assert name is None

    @pytest.mark.asyncio
    async def test_delete_key_not_found(self):
        deleted = await mailbox_db.delete_api_key("nonexistent")
        assert deleted is False


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


# ---------------------------------------------------------------------------
# FastAPI — API key registration and dynamic auth
# ---------------------------------------------------------------------------


class TestAPIKeyRegistration:
    @pytest.mark.asyncio
    async def test_register_key(self, client):
        resp = await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "new-key-curie"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "curie"
        assert data["message"] == "Key registered"

    @pytest.mark.asyncio
    async def test_register_key_duplicate_name(self, client):
        await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "key-1"},
            headers=DOOT_HEADERS,
        )
        resp = await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "key-2"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_key_no_auth(self, client):
        resp = await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "key-1"},
        )
        assert resp.status_code == 422  # missing header

    @pytest.mark.asyncio
    async def test_list_keys(self, client):
        await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "key-1"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/keys",
            json={"name": "darwin", "key": "key-2"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get("/api/v1/keys", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) == 2
        names = [k["name"] for k in keys]
        assert "curie" in names
        assert "darwin" in names

    @pytest.mark.asyncio
    async def test_list_keys_no_key_values_exposed(self, client):
        await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "super-secret-key"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get("/api/v1/keys", headers=DOOT_HEADERS)
        keys = resp.json()
        for k in keys:
            assert "key" not in k

    @pytest.mark.asyncio
    async def test_auth_with_db_registered_key(self, client):
        """A key registered via the API should be usable for auth."""
        # Register a new key
        await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "dynamic-key-curie"},
            headers=DOOT_HEADERS,
        )
        # Use the new key to send a message
        resp = await client.post(
            "/api/v1/messages",
            json={"recipients": ["doot"], "body": "Hello from curie"},
            headers={"Authorization": "Bearer dynamic-key-curie"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Message sent"

    @pytest.mark.asyncio
    async def test_auth_with_db_key_sender_identity(self, client):
        """Messages sent with a DB-registered key should have correct sender."""
        await client.post(
            "/api/v1/keys",
            json={"name": "curie", "key": "dynamic-key-curie"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["doot"], "body": "Hello from curie"},
            headers={"Authorization": "Bearer dynamic-key-curie"},
        )
        # Check doot's inbox
        resp = await client.get("/api/v1/messages", headers=DOOT_HEADERS)
        messages = resp.json()
        assert len(messages) == 1
        assert messages[0]["sender"] == "curie"


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
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
            instance = self._make_async_client(get_resp=mock_resp)
            MockClient.return_value = instance
            result = await self.client.browse_feed()
            assert len(result) == 1
            assert result[0]["sender"] == "doot"

    @pytest.mark.asyncio
    async def test_browse_feed_with_params(self):
        mock_resp = self._make_mock_resp([])
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
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
        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
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

        with patch("clade.communication.mailbox_client.httpx.AsyncClient") as MockClient:
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
        tools = _make_tools(None)
        result = await tools["browse_feed"]()
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_browse_feed_empty(self):
        mock_client = AsyncMock()
        mock_client.browse_feed.return_value = []
        tools = _make_tools(mock_client)
        result = await tools["browse_feed"]()
        assert "No messages" in result

    @pytest.mark.asyncio
    async def test_browse_feed_with_messages(self):
        mock_client = AsyncMock()
        mock_client.browse_feed.return_value = [
            {
                "id": 1, "sender": "doot", "subject": "Hello",
                "body": "Test message", "created_at": "2026-02-07T00:00:00Z",
                "recipients": ["oppy", "jerry"],
                "read_by": [{"brother": "oppy", "read_at": "2026-02-07T01:00:00Z"}],
            }
        ]
        tools = _make_tools(mock_client)
        result = await tools["browse_feed"]()
        assert "#1" in result
        assert "doot" in result
        assert "oppy, jerry" in result
        assert "Hello" in result
        assert "Read by: oppy" in result

    @pytest.mark.asyncio
    async def test_browse_feed_no_read_by(self):
        mock_client = AsyncMock()
        mock_client.browse_feed.return_value = [
            {
                "id": 1, "sender": "doot", "subject": "Hello",
                "body": "Test", "created_at": "2026-02-07T00:00:00Z",
                "recipients": ["oppy"], "read_by": [],
            }
        ]
        tools = _make_tools(mock_client)
        result = await tools["browse_feed"]()
        assert "Read by" not in result

    @pytest.mark.asyncio
    async def test_browse_feed_error(self):
        mock_client = AsyncMock()
        mock_client.browse_feed.side_effect = Exception("Connection refused")
        tools = _make_tools(mock_client)
        result = await tools["browse_feed"]()
        assert "Error" in result


class TestMCPReadMessageWithReadBy:
    @pytest.mark.asyncio
    async def test_read_message_shows_read_by(self):
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
        tools = _make_tools(mock_client)
        result = await tools["read_message"](1)
        assert "Read by: doot, jerry" in result

    @pytest.mark.asyncio
    async def test_read_message_no_read_by(self):
        mock_client = AsyncMock()
        mock_client.read_message.return_value = {
            "id": 1, "sender": "oppy", "subject": "Test",
            "body": "Body",
            "created_at": "2026-02-07T10:00:00Z",
            "recipients": ["doot"], "is_read": False,
            "read_by": [],
        }
        tools = _make_tools(mock_client)
        result = await tools["read_message"](1)
        assert "Read by" not in result


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
