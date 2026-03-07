"""Tests for centralized brother permissions stored in the Hearth (card #88)."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

os.environ.setdefault(
    "MAILBOX_API_KEYS",
    "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian",
)

from httpx import ASGITransport, AsyncClient

from hearth.app import app
from hearth import db as hearth_db


DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}
IAN_HEADERS = {"Authorization": "Bearer test-key-ian"}


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


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------


class TestDatabaseEmberPermissions:
    @pytest.mark.asyncio
    async def test_permission_flags_default_empty(self):
        """Newly registered ember has empty permission_flags by default."""
        entry = await hearth_db.upsert_ember("oppy", "http://oppy:8100")
        assert entry["permission_flags"] == ""

    @pytest.mark.asyncio
    async def test_update_permission_flags(self):
        """update_ember_permissions stores and returns the new flags."""
        await hearth_db.upsert_ember("oppy", "http://oppy:8100")
        entry = await hearth_db.update_ember_permissions("oppy", "--dangerously-skip-permissions")
        assert entry is not None
        assert entry["permission_flags"] == "--dangerously-skip-permissions"

    @pytest.mark.asyncio
    async def test_update_permissions_not_found(self):
        """update_ember_permissions returns None for unknown brother."""
        result = await hearth_db.update_ember_permissions("nobody", "--dangerously-skip-permissions")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_ember_includes_permissions(self):
        """get_ember returns permission_flags."""
        await hearth_db.upsert_ember("oppy", "http://oppy:8100")
        await hearth_db.update_ember_permissions("oppy", "--permission-mode acceptEdits")
        entry = await hearth_db.get_ember("oppy")
        assert entry["permission_flags"] == "--permission-mode acceptEdits"

    @pytest.mark.asyncio
    async def test_get_embers_includes_permissions(self):
        """get_embers list includes permission_flags for all entries."""
        await hearth_db.upsert_ember("oppy", "http://oppy:8100")
        await hearth_db.update_ember_permissions("oppy", "--dangerously-skip-permissions")
        await hearth_db.upsert_ember("jerry", "http://jerry:8100")

        embers = await hearth_db.get_embers()
        oppy = next(e for e in embers if e["name"] == "oppy")
        jerry = next(e for e in embers if e["name"] == "jerry")
        assert oppy["permission_flags"] == "--dangerously-skip-permissions"
        assert jerry["permission_flags"] == ""

    @pytest.mark.asyncio
    async def test_upsert_does_not_reset_permissions(self):
        """Re-registering an ember (upsert) preserves existing permission_flags."""
        await hearth_db.upsert_ember("oppy", "http://oppy:8100")
        await hearth_db.update_ember_permissions("oppy", "--dangerously-skip-permissions")
        # Re-upsert with a new URL (simulating ember restart)
        await hearth_db.upsert_ember("oppy", "http://oppy-new:8100")
        entry = await hearth_db.get_ember("oppy")
        assert entry["permission_flags"] == "--dangerously-skip-permissions"
        assert entry["ember_url"] == "http://oppy-new:8100"


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


class TestAPIEmberPermissions:
    @pytest.mark.asyncio
    async def test_put_permissions(self, client):
        """PUT /api/v1/embers/{name}/permissions sets permission_flags."""
        # Register ember first
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )
        resp = await client.put(
            "/api/v1/embers/oppy/permissions",
            json={"permission_flags": "--dangerously-skip-permissions"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["permission_flags"] == "--dangerously-skip-permissions"

    @pytest.mark.asyncio
    async def test_put_permissions_not_found(self, client):
        """PUT /api/v1/embers/{name}/permissions returns 404 if ember not registered."""
        resp = await client.put(
            "/api/v1/embers/nobody/permissions",
            json={"permission_flags": "--dangerously-skip-permissions"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_permissions(self, client):
        """GET /api/v1/embers/{name}/permissions returns permission_flags."""
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )
        await client.put(
            "/api/v1/embers/oppy/permissions",
            json={"permission_flags": "--permission-mode acceptEdits"},
            headers=OPPY_HEADERS,
        )
        resp = await client.get("/api/v1/embers/oppy/permissions", headers=OPPY_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "oppy"
        assert data["permission_flags"] == "--permission-mode acceptEdits"

    @pytest.mark.asyncio
    async def test_get_permissions_not_found(self, client):
        """GET /api/v1/embers/{name}/permissions returns 404 if not registered."""
        resp = await client.get("/api/v1/embers/nobody/permissions", headers=OPPY_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_ember_includes_permission_flags(self, client):
        """GET /api/v1/embers/{name} returns permission_flags in the response."""
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )
        await client.put(
            "/api/v1/embers/oppy/permissions",
            json={"permission_flags": "--dangerously-skip-permissions"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get("/api/v1/embers/oppy", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["permission_flags"] == "--dangerously-skip-permissions"

    @pytest.mark.asyncio
    async def test_empty_permission_flags_allowed(self, client):
        """Setting permission_flags to empty string (CC defaults) is valid."""
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )
        await client.put(
            "/api/v1/embers/oppy/permissions",
            json={"permission_flags": "--dangerously-skip-permissions"},
            headers=DOOT_HEADERS,
        )
        resp = await client.put(
            "/api/v1/embers/oppy/permissions",
            json={"permission_flags": ""},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["permission_flags"] == ""

    @pytest.mark.asyncio
    async def test_oppy_can_set_own_permissions(self, client):
        """An ember brother can set their own permissions."""
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )
        resp = await client.put(
            "/api/v1/embers/oppy/permissions",
            json={"permission_flags": "--dangerously-skip-permissions"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_upsert_preserves_permissions(self, client):
        """Re-registering an ember via PUT /embers/{name} does not reset permissions."""
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )
        await client.put(
            "/api/v1/embers/oppy/permissions",
            json={"permission_flags": "--dangerously-skip-permissions"},
            headers=DOOT_HEADERS,
        )
        # Re-register with new URL (Ember restart)
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy-new:8100"},
            headers=DOOT_HEADERS,
        )
        resp = await client.get("/api/v1/embers/oppy", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ember_url"] == "http://oppy-new:8100"
        assert data["permission_flags"] == "--dangerously-skip-permissions"
