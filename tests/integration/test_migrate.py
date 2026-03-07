"""Integration tests for the migrate import/export API endpoints."""

import os

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
# Import endpoint
# ---------------------------------------------------------------------------


class TestMigrateImport:
    @pytest.mark.asyncio
    async def test_import_cards(self, client):
        payload = {
            "schema_version": 1,
            "exported_at": "2026-01-01T00:00:00Z",
            "source_hearth": "https://old-hearth",
            "data": {
                "cards": [
                    {
                        "id": 42,
                        "title": "Migrated Card",
                        "description": "From the old Clade",
                        "col": "in_progress",
                        "priority": "high",
                        "creator": "doot",
                        "assignee": "oppy",
                        "created_at": "2025-12-01T10:00:00Z",
                        "updated_at": "2025-12-02T10:00:00Z",
                        "labels": ["feature", "urgent"],
                        "links": [],
                        "project": "clade",
                    }
                ],
                "morsels": [],
                "tasks": [],
                "messages": [],
            },
        }
        resp = await client.post("/api/v1/migrate/import", json=payload, headers=DOOT_HEADERS)
        assert resp.status_code == 200
        result = resp.json()
        assert result["imported_cards"] == 1
        assert result["errors"] == []

        # Verify card is accessible with original ID
        card_resp = await client.get("/api/v1/kanban/cards/42", headers=DOOT_HEADERS)
        assert card_resp.status_code == 200
        card = card_resp.json()
        assert card["id"] == 42
        assert card["title"] == "Migrated Card"
        assert card["col"] == "in_progress"
        assert card["created_at"] == "2025-12-01T10:00:00Z"
        assert "feature" in card["labels"]

    @pytest.mark.asyncio
    async def test_import_morsels(self, client):
        payload = {
            "schema_version": 1,
            "exported_at": "2026-01-01T00:00:00Z",
            "source_hearth": "https://old-hearth",
            "data": {
                "cards": [],
                "morsels": [
                    {
                        "id": 99,
                        "creator": "oppy",
                        "body": "Important institutional knowledge",
                        "created_at": "2025-11-15T08:30:00Z",
                        "tags": ["design", "important"],
                        "links": [],
                    }
                ],
                "tasks": [],
                "messages": [],
            },
        }
        resp = await client.post("/api/v1/migrate/import", json=payload, headers=OPPY_HEADERS)
        assert resp.status_code == 200
        result = resp.json()
        assert result["imported_morsels"] == 1
        assert result["errors"] == []

        # Verify morsel with original ID and timestamp
        morsel_resp = await client.get("/api/v1/morsels/99", headers=OPPY_HEADERS)
        assert morsel_resp.status_code == 200
        morsel = morsel_resp.json()
        assert morsel["id"] == 99
        assert morsel["body"] == "Important institutional knowledge"
        assert morsel["created_at"] == "2025-11-15T08:30:00Z"
        assert "design" in morsel["tags"]

    @pytest.mark.asyncio
    async def test_import_cards_and_morsels_with_links(self, client):
        """Import morsels and cards that link to each other — links preserved."""
        payload = {
            "schema_version": 1,
            "exported_at": "2026-01-01T00:00:00Z",
            "source_hearth": "https://old-hearth",
            "data": {
                "cards": [
                    {
                        "id": 10,
                        "title": "Card with morsel link",
                        "description": "",
                        "col": "todo",
                        "priority": "normal",
                        "creator": "doot",
                        "assignee": None,
                        "created_at": "2025-12-01T00:00:00Z",
                        "updated_at": "2025-12-01T00:00:00Z",
                        "labels": [],
                        "links": [{"object_type": "morsel", "object_id": "20"}],
                        "project": None,
                    }
                ],
                "morsels": [
                    {
                        "id": 20,
                        "creator": "oppy",
                        "body": "Linked morsel",
                        "created_at": "2025-12-01T00:00:00Z",
                        "tags": [],
                        "links": [],
                    }
                ],
                "tasks": [],
                "messages": [],
            },
        }
        resp = await client.post("/api/v1/migrate/import", json=payload, headers=DOOT_HEADERS)
        assert resp.status_code == 200
        result = resp.json()
        assert result["imported_cards"] == 1
        assert result["imported_morsels"] == 1
        assert result["errors"] == []

        card_resp = await client.get("/api/v1/kanban/cards/10", headers=DOOT_HEADERS)
        card = card_resp.json()
        assert any(lnk["object_type"] == "morsel" for lnk in card["links"])

    @pytest.mark.asyncio
    async def test_import_rejects_unknown_schema_version(self, client):
        payload = {
            "schema_version": 99,
            "exported_at": "2026-01-01T00:00:00Z",
            "source_hearth": "https://old-hearth",
            "data": {"cards": [], "morsels": [], "tasks": [], "messages": []},
        }
        resp = await client.post("/api/v1/migrate/import", json=payload, headers=DOOT_HEADERS)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_import_idempotent_on_clean_target(self, client):
        """Re-importing the same data is safe (INSERT OR IGNORE)."""
        payload = {
            "schema_version": 1,
            "exported_at": "2026-01-01T00:00:00Z",
            "source_hearth": "https://old-hearth",
            "data": {
                "cards": [
                    {
                        "id": 7,
                        "title": "Duplicate test",
                        "description": "",
                        "col": "backlog",
                        "priority": "normal",
                        "creator": "doot",
                        "assignee": None,
                        "created_at": "2025-12-01T00:00:00Z",
                        "updated_at": "2025-12-01T00:00:00Z",
                        "labels": [],
                        "links": [],
                        "project": None,
                    }
                ],
                "morsels": [],
                "tasks": [],
                "messages": [],
            },
        }
        resp1 = await client.post("/api/v1/migrate/import", json=payload, headers=DOOT_HEADERS)
        assert resp1.status_code == 200
        resp2 = await client.post("/api/v1/migrate/import", json=payload, headers=DOOT_HEADERS)
        assert resp2.status_code == 200
        result2 = resp2.json()
        # Second import: card already exists so INSERT OR IGNORE skips it.
        # imported_cards will be 1 (no error), and no errors raised.
        assert result2["errors"] == []

    @pytest.mark.asyncio
    async def test_import_empty_payload(self, client):
        payload = {
            "schema_version": 1,
            "exported_at": "2026-01-01T00:00:00Z",
            "source_hearth": "https://old-hearth",
            "data": {"cards": [], "morsels": [], "tasks": [], "messages": []},
        }
        resp = await client.post("/api/v1/migrate/import", json=payload, headers=DOOT_HEADERS)
        assert resp.status_code == 200
        result = resp.json()
        assert result["imported_cards"] == 0
        assert result["imported_morsels"] == 0
        assert result["imported_tasks"] == 0
        assert result["imported_messages"] == 0


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


class TestMigrateExport:
    @pytest.mark.asyncio
    async def test_export_empty_db(self, client):
        resp = await client.get("/api/v1/migrate/export", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_version"] == 1
        assert "exported_at" in data
        assert data["data"]["cards"] == []
        assert data["data"]["morsels"] == []

    @pytest.mark.asyncio
    async def test_export_includes_cards_and_morsels_by_default(self, client):
        # Create a card and a morsel
        await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Export test card", "col": "todo"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/morsels",
            json={"body": "Export test morsel", "tags": ["test"]},
            headers=OPPY_HEADERS,
        )

        resp = await client.get("/api/v1/migrate/export", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["cards"]) == 1
        assert len(data["data"]["morsels"]) == 1
        # Tasks not included by default
        assert data["data"]["tasks"] == []
        assert data["data"]["messages"] == []

    @pytest.mark.asyncio
    async def test_export_include_tasks(self, client):
        resp = await client.get(
            "/api/v1/migrate/export",
            params={"include": "cards,morsels,tasks"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        # tasks key present in output (even if empty)
        assert "tasks" in data["data"]

    @pytest.mark.asyncio
    async def test_export_roundtrip(self, client):
        """Export from one 'hearth', import into same (empty) hearth — data survives."""
        # Create original data
        card_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Roundtrip card", "col": "done", "priority": "high", "labels": ["alpha"]},
            headers=DOOT_HEADERS,
        )
        morsel_resp = await client.post(
            "/api/v1/morsels",
            json={"body": "Roundtrip morsel", "tags": ["beta"]},
            headers=OPPY_HEADERS,
        )
        original_card_id = card_resp.json()["id"]
        original_morsel_id = morsel_resp.json()["id"]

        # Export
        export_resp = await client.get("/api/v1/migrate/export", headers=DOOT_HEADERS)
        exported = export_resp.json()

        # Wipe DB and re-import
        from hearth import db as hearth_db
        import aiosqlite
        async with aiosqlite.connect(hearth_db.DB_PATH) as db:
            await db.execute("DELETE FROM kanban_card_labels")
            await db.execute("DELETE FROM kanban_card_links")
            await db.execute("DELETE FROM kanban_cards")
            await db.execute("DELETE FROM morsel_tags")
            await db.execute("DELETE FROM morsel_links")
            await db.execute("DELETE FROM morsels")
            await db.commit()

        import_payload = {
            "schema_version": exported["schema_version"],
            "exported_at": exported["exported_at"],
            "source_hearth": exported.get("source_hearth", "unknown"),
            "data": exported["data"],
        }
        import_resp = await client.post(
            "/api/v1/migrate/import", json=import_payload, headers=DOOT_HEADERS
        )
        assert import_resp.status_code == 200
        result = import_resp.json()
        assert result["imported_cards"] == 1
        assert result["imported_morsels"] == 1

        # Original IDs preserved
        card_check = await client.get(f"/api/v1/kanban/cards/{original_card_id}", headers=DOOT_HEADERS)
        assert card_check.status_code == 200
        assert card_check.json()["title"] == "Roundtrip card"

        morsel_check = await client.get(f"/api/v1/morsels/{original_morsel_id}", headers=OPPY_HEADERS)
        assert morsel_check.status_code == 200
        assert morsel_check.json()["body"] == "Roundtrip morsel"


# ---------------------------------------------------------------------------
# DB-level import functions
# ---------------------------------------------------------------------------


class TestDBImportFunctions:
    @pytest.mark.asyncio
    async def test_import_morsel_raw(self):
        morsel = {
            "id": 500,
            "creator": "oppy",
            "body": "Raw import test",
            "created_at": "2024-06-01T12:00:00Z",
            "tags": ["raw", "test"],
            "links": [],
        }
        await hearth_db.import_morsel(morsel)
        result = await hearth_db.get_morsel(500)
        assert result is not None
        assert result["id"] == 500
        assert result["body"] == "Raw import test"
        assert result["created_at"] == "2024-06-01T12:00:00Z"
        assert "raw" in result["tags"]

    @pytest.mark.asyncio
    async def test_import_card_raw(self):
        card = {
            "id": 300,
            "creator": "doot",
            "title": "Raw card",
            "description": "Imported directly",
            "col": "done",
            "priority": "high",
            "assignee": "oppy",
            "project": "clade",
            "created_at": "2024-01-15T08:00:00Z",
            "updated_at": "2024-01-16T08:00:00Z",
            "labels": ["imported"],
            "links": [],
        }
        await hearth_db.import_card(card)
        result = await hearth_db.get_card(300)
        assert result is not None
        assert result["id"] == 300
        assert result["title"] == "Raw card"
        assert result["col"] == "done"
        assert result["created_at"] == "2024-01-15T08:00:00Z"
        assert "imported" in result["labels"]

    @pytest.mark.asyncio
    async def test_import_morsel_idempotent(self):
        morsel = {
            "id": 600,
            "creator": "jerry",
            "body": "Idempotent test",
            "created_at": "2024-03-01T00:00:00Z",
            "tags": [],
            "links": [],
        }
        await hearth_db.import_morsel(morsel)
        await hearth_db.import_morsel(morsel)  # Should not raise
        result = await hearth_db.get_morsel(600)
        assert result["id"] == 600
