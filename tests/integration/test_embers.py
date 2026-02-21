"""Tests for the Ember registry: database, API, and status merge."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

os.environ.setdefault("MAILBOX_API_KEYS", "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian")

from httpx import ASGITransport, AsyncClient

from hearth.app import app
from hearth import db as hearth_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
# Embers — database layer
# ---------------------------------------------------------------------------


class TestDatabaseEmbers:
    @pytest.mark.asyncio
    async def test_upsert_insert(self):
        entry = await hearth_db.upsert_ember("oppy", "http://100.71.57.52:8100")
        assert entry["name"] == "oppy"
        assert entry["ember_url"] == "http://100.71.57.52:8100"
        assert entry["created_at"] is not None
        assert entry["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_upsert_update(self):
        await hearth_db.upsert_ember("oppy", "http://old:8100")
        entry = await hearth_db.upsert_ember("oppy", "http://new:8100")
        assert entry["ember_url"] == "http://new:8100"

        # Only one entry in DB
        all_embers = await hearth_db.get_embers()
        assert len(all_embers) == 1

    @pytest.mark.asyncio
    async def test_get_embers(self):
        await hearth_db.upsert_ember("jerry", "http://jerry:8100")
        await hearth_db.upsert_ember("oppy", "http://oppy:8100")

        embers = await hearth_db.get_embers()
        assert len(embers) == 2
        # Ordered by name
        assert embers[0]["name"] == "jerry"
        assert embers[1]["name"] == "oppy"

    @pytest.mark.asyncio
    async def test_delete_ember(self):
        await hearth_db.upsert_ember("oppy", "http://oppy:8100")
        deleted = await hearth_db.delete_ember("oppy")
        assert deleted is True

        embers = await hearth_db.get_embers()
        assert len(embers) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        deleted = await hearth_db.delete_ember("nobody")
        assert deleted is False


# ---------------------------------------------------------------------------
# Embers — API endpoints
# ---------------------------------------------------------------------------


class TestAPIEmbers:
    @pytest.mark.asyncio
    async def test_put_create(self, client):
        resp = await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://100.71.57.52:8100"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "oppy"
        assert data["ember_url"] == "http://100.71.57.52:8100"

    @pytest.mark.asyncio
    async def test_put_update(self, client):
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://old:8100"},
            headers=DOOT_HEADERS,
        )
        resp = await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://new:8100"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["ember_url"] == "http://new:8100"

    @pytest.mark.asyncio
    async def test_get_list(self, client):
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )
        await client.put(
            "/api/v1/embers/jerry",
            json={"ember_url": "http://jerry:8100"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get("/api/v1/embers", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        embers = resp.json()
        assert len(embers) == 2

    @pytest.mark.asyncio
    async def test_delete_admin_only(self, client):
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=DOOT_HEADERS,
        )

        # Non-admin cannot delete
        resp = await client.delete("/api/v1/embers/oppy", headers=OPPY_HEADERS)
        assert resp.status_code == 403

        # Admin can delete
        resp = await client.delete("/api/v1/embers/oppy", headers=DOOT_HEADERS)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client):
        resp = await client.delete("/api/v1/embers/nobody", headers=DOOT_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_ian_is_admin(self, client):
        """Ian should also be able to delete (admin)."""
        await client.put(
            "/api/v1/embers/oppy",
            json={"ember_url": "http://oppy:8100"},
            headers=IAN_HEADERS,
        )
        resp = await client.delete("/api/v1/embers/oppy", headers=IAN_HEADERS)
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Ember status — merge env + DB
# ---------------------------------------------------------------------------


class TestEmberStatusMerge:
    @pytest.mark.asyncio
    @patch("hearth.app.EMBER_URLS", {})
    async def test_db_only(self, client):
        """DB-registered embers show in status when env is empty."""
        await hearth_db.upsert_ember("oppy", "http://oppy:8100")

        # The actual health check will fail (no real server), but we test the merge
        resp = await client.get("/api/v1/embers/status", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "oppy" in data["embers"]

    @pytest.mark.asyncio
    @patch("hearth.app.EMBER_URLS", {"oppy": "http://env-oppy:8100"})
    async def test_env_only(self, client):
        """Env-var embers show when DB is empty."""
        resp = await client.get("/api/v1/embers/status", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "oppy" in data["embers"]

    @pytest.mark.asyncio
    @patch("hearth.app.EMBER_URLS", {"oppy": "http://env-oppy:8100"})
    async def test_db_wins_on_conflict(self, client):
        """When both env and DB have the same name, DB wins."""
        await hearth_db.upsert_ember("oppy", "http://db-oppy:8100")

        called_urls = []

        class MockAsyncClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url):
                called_urls.append(url)
                resp = MagicMock()
                resp.json.return_value = {"active_tasks": 0, "uptime_seconds": 100}
                resp.raise_for_status.return_value = None
                return resp

        with patch("httpx.AsyncClient", MockAsyncClient):
            resp = await client.get("/api/v1/embers/status", headers=DOOT_HEADERS)

        assert resp.status_code == 200
        # DB URL should have won
        assert any("db-oppy" in url for url in called_urls)
        assert not any("env-oppy" in url for url in called_urls)

    @pytest.mark.asyncio
    @patch("hearth.app.EMBER_URLS", {"oppy": "http://env-oppy:8100"})
    async def test_merged_set(self, client):
        """Both env and DB entries appear when names differ."""
        await hearth_db.upsert_ember("jerry", "http://db-jerry:8100")

        resp = await client.get("/api/v1/embers/status", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "oppy" in data["embers"]
        assert "jerry" in data["embers"]
