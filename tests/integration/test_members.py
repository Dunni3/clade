"""Tests for the member activity endpoint."""

import os

import pytest
import pytest_asyncio

os.environ["MAILBOX_API_KEYS"] = "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian"

from hearth import config as hearth_config
hearth_config.API_KEYS = hearth_config.parse_api_keys(os.environ["MAILBOX_API_KEYS"])

from httpx import ASGITransport, AsyncClient

from hearth.app import app
from hearth import db as hearth_db


DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}

@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = hearth_db.DB_PATH
    hearth_db.DB_PATH = db_path
    await hearth_db.init_db()
    yield db_path
    hearth_db.DB_PATH = original


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestMemberActivityDB:
    @pytest.mark.asyncio
    async def test_empty_state(self):
        """No registered keys (via DB) returns empty list."""
        activity = await hearth_db.get_member_activity()
        # api_keys table is empty (keys are in env vars, not DB) — so returns []
        assert isinstance(activity, list)

    @pytest.mark.asyncio
    async def test_with_registered_keys(self):
        """Members from api_keys table get activity stats."""
        await hearth_db.insert_api_key("alice", "key-alice")
        await hearth_db.insert_api_key("bob", "key-bob")

        activity = await hearth_db.get_member_activity()
        assert len(activity) == 2
        names = [m["name"] for m in activity]
        assert "alice" in names
        assert "bob" in names

        alice = next(m for m in activity if m["name"] == "alice")
        assert alice["messages_sent"] == 0
        assert alice["active_tasks"] == 0
        assert alice["completed_tasks"] == 0
        assert alice["failed_tasks"] == 0
        assert alice["last_message_at"] is None
        assert alice["last_task_at"] is None

    @pytest.mark.asyncio
    async def test_with_messages_and_tasks(self):
        """Activity counts reflect actual messages and tasks."""
        await hearth_db.insert_api_key("alice", "key-alice")
        await hearth_db.insert_api_key("bob", "key-bob")

        # Alice sends 2 messages
        await hearth_db.insert_message("alice", "Hi", "Hello bob", ["bob"])
        await hearth_db.insert_message("alice", "Re", "Another", ["bob"])

        # Bob sends 1 message
        await hearth_db.insert_message("bob", "Hey", "Hey alice", ["alice"])

        # Create tasks: alice creates, bob is assignee
        task_id = await hearth_db.insert_task(
            creator="alice", assignee="bob", prompt="Do stuff"
        )
        await hearth_db.update_task(task_id, status="completed")

        task_id2 = await hearth_db.insert_task(
            creator="alice", assignee="bob", prompt="More stuff"
        )
        await hearth_db.update_task(task_id2, status="failed")

        activity = await hearth_db.get_member_activity()
        alice = next(m for m in activity if m["name"] == "alice")
        bob = next(m for m in activity if m["name"] == "bob")

        assert alice["messages_sent"] == 2
        assert alice["last_message_at"] is not None
        # Alice is creator of both tasks
        assert alice["completed_tasks"] == 1
        assert alice["failed_tasks"] == 1

        assert bob["messages_sent"] == 1
        # Bob is assignee of both tasks
        assert bob["completed_tasks"] == 1
        assert bob["failed_tasks"] == 1


class TestMemberActivityAPI:
    @pytest.mark.asyncio
    async def test_endpoint_requires_auth(self, client):
        # Missing header → 422, invalid key → 401
        resp = await client.get("/api/v1/members/activity")
        assert resp.status_code == 422

        resp = await client.get(
            "/api/v1/members/activity",
            headers={"Authorization": "Bearer bad-key"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_endpoint_returns_members(self, client):
        resp = await client.get("/api/v1/members/activity", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "members" in data
        assert isinstance(data["members"], list)

    @pytest.mark.asyncio
    async def test_endpoint_with_data(self, client):
        # Register a key in the DB so it shows up
        await hearth_db.insert_api_key("testmember", "key-testmember")

        # Send a message as doot (via env-based auth)
        await client.post(
            "/api/v1/messages",
            json={"recipients": ["testmember"], "body": "Hello", "subject": "Test"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get("/api/v1/members/activity", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        members = data["members"]

        # testmember should be in the list (it's in the DB api_keys table)
        names = [m["name"] for m in members]
        assert "testmember" in names
